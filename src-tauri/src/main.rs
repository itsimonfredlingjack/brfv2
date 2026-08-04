//! Träff — Fedora desktop shell.
//!
//! The shell owns exactly three things: the packaged Python runtime's
//! lifecycle, the webview that talks to it over a random loopback origin, and
//! the operational surfaces a user cannot reach from inside a web page
//! (startup failure, backend death, restart after a staged restore).  All
//! product logic stays in the verified React and Python layers.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use std::{
    env, fs,
    io::{self, BufRead, BufReader},
    path::{Path, PathBuf},
    process::{Child, Command, ExitStatus, Stdio},
    sync::{
        atomic::{AtomicBool, Ordering},
        mpsc, Arc, Mutex,
    },
    thread,
    time::{Duration, Instant},
};
use tauri::{
    webview::NewWindowResponse, AppHandle, Manager, RunEvent, WebviewUrl, WebviewWindowBuilder,
};

const STARTUP_SCHEMA: &str = "brfv2-desktop-startup/v1";
const STARTUP_TIMEOUT: Duration = Duration::from_secs(120);
const SHUTDOWN_GRACE: Duration = Duration::from_secs(3);
const SUPERVISOR_INTERVAL: Duration = Duration::from_millis(250);

/// The backend exits with this code to ask the shell for a full restart.  It
/// is the only in-band control channel between the HTTP application and the
/// shell, which is why no Tauri IPC capability has to be granted to the remote
/// origin for restore-after-restart to work.
const RESTART_EXIT_CODE: i32 = 86;

const DEFAULT_WIDTH: f64 = 1440.0;
const DEFAULT_HEIGHT: f64 = 920.0;
const MIN_WIDTH: f64 = 860.0;
const MIN_HEIGHT: f64 = 620.0;

type BoxError = Box<dyn std::error::Error + Send + Sync>;

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
struct StartupContract {
    schema: String,
    status: String,
    host: String,
    port: u16,
    origin: String,
}

impl StartupContract {
    fn validate(self) -> Result<Self, BoxError> {
        let expected_origin = format!("http://127.0.0.1:{}", self.port);
        if self.schema != STARTUP_SCHEMA
            || self.status != "ready"
            || self.host != "127.0.0.1"
            || self.port == 0
            || self.origin != expected_origin
        {
            return Err(format!("unsafe or invalid desktop startup contract: {self:?}").into());
        }
        Ok(self)
    }
}

// ---------------------------------------------------------------------------
// Runtime location
// ---------------------------------------------------------------------------

/// Where the interpreter, the backend package, the built UI and the bundled
/// embedder weights live for this launch.
#[derive(Clone, Debug, PartialEq, Eq)]
struct RuntimeLayout {
    python: PathBuf,
    backend_dir: PathBuf,
    dist: PathBuf,
    model2vec: Option<PathBuf>,
    packaged: bool,
}

fn packaged_layout(resource_dir: &Path) -> Option<RuntimeLayout> {
    let runtime = resource_dir.join("runtime");
    let python = runtime.join("python/bin/python3");
    let backend_dir = runtime.join("backend");
    let dist = resource_dir.join("ui");
    let model2vec = runtime.join("models/potion-multilingual-128M");
    if !python.is_file() || !backend_dir.join("app/desktop.py").is_file() {
        return None;
    }
    if !dist.join("index.html").is_file() {
        return None;
    }
    // The weights are as mandatory as the interpreter.  Treating them as
    // optional would let an incomplete installation fall through to
    // model2vec's default behaviour, which is to fetch the model from
    // huggingface.co on first use — precisely the hidden egress this product
    // promises not to do.  An incomplete bundle must fail visibly instead.
    if !model2vec.is_dir() {
        return None;
    }
    Some(RuntimeLayout {
        python,
        backend_dir,
        dist,
        model2vec: Some(model2vec),
        packaged: true,
    })
}

fn is_repo_root(path: &Path) -> bool {
    path.join("backend/.venv/bin/python").is_file()
        && path.join("backend/app/desktop.py").is_file()
        && path.join("brfv2-mockup/dist/index.html").is_file()
}

fn candidate_and_ancestors(path: PathBuf) -> impl Iterator<Item = PathBuf> {
    let mut candidates = Vec::new();
    let mut current = Some(path.as_path());
    while let Some(candidate) = current {
        candidates.push(candidate.to_path_buf());
        current = candidate.parent();
    }
    candidates.into_iter()
}

fn find_repo_root() -> Option<PathBuf> {
    if let Some(explicit) = env::var_os("BRFV2_REPO_ROOT") {
        let path = PathBuf::from(explicit);
        return is_repo_root(&path).then(|| path.canonicalize().ok()).flatten();
    }
    let mut roots = Vec::new();
    if let Ok(cwd) = env::current_dir() {
        roots.extend(candidate_and_ancestors(cwd));
    }
    if let Ok(executable) = env::current_exe() {
        if let Some(parent) = executable.parent() {
            roots.extend(candidate_and_ancestors(parent.to_path_buf()));
        }
    }
    roots
        .into_iter()
        .find(|candidate| is_repo_root(candidate))
        .and_then(|candidate| candidate.canonicalize().ok())
}

fn checkout_layout(repo_root: &Path) -> RuntimeLayout {
    // Prefer the staged bundle's weights when `make desktop-runtime` has run:
    // they are the pinned revision, verified by SHA-256, and using them makes a
    // checkout run resolve the embedder exactly the way the installed
    // application does. Falling back to the developer's ordinary Hugging Face
    // cache also means falling back to model2vec's hub resolution, which is not
    // safe to enter from two request threads at once.
    let staged = repo_root.join("src-tauri/runtime/models/potion-multilingual-128M");
    RuntimeLayout {
        python: repo_root.join("backend/.venv/bin/python"),
        backend_dir: repo_root.join("backend"),
        dist: repo_root.join("brfv2-mockup/dist"),
        model2vec: staged.is_dir().then_some(staged),
        packaged: false,
    }
}

/// Prefer the installed bundle, fall back to a development checkout.
fn resolve_runtime(resource_dir: Option<&Path>) -> Result<RuntimeLayout, BoxError> {
    if let Some(dir) = resource_dir {
        if let Some(layout) = packaged_layout(dir) {
            return Ok(layout);
        }
    }
    if let Some(repo_root) = find_repo_root() {
        return Ok(checkout_layout(&repo_root));
    }
    Err(concat!(
        "Hittade varken den installerade körmiljön eller en utvecklingscheckout. ",
        "Installera om applikationen, eller kör den från en checkout där ",
        "`make desktop-build` har körts."
    )
    .into())
}

// ---------------------------------------------------------------------------
// Backend process
// ---------------------------------------------------------------------------

struct OwnedBackend {
    child: Child,
    contract: StartupContract,
}

impl OwnedBackend {
    fn not_ready(child: Child) -> Self {
        OwnedBackend {
            child,
            contract: StartupContract {
                schema: STARTUP_SCHEMA.into(),
                status: "not-ready".into(),
                host: "127.0.0.1".into(),
                port: 1,
                origin: "http://127.0.0.1:1".into(),
            },
        }
    }

    fn terminate(&mut self) {
        if matches!(self.child.try_wait(), Ok(Some(_))) {
            return;
        }

        let process_group = -(self.child.id() as i32);
        // The Python process starts its own group.  Signal the entire owned
        // group so a future adapter subprocess cannot outlive the shell.
        unsafe {
            libc::kill(process_group, libc::SIGTERM);
        }
        let deadline = Instant::now() + SHUTDOWN_GRACE;
        while Instant::now() < deadline {
            match self.child.try_wait() {
                Ok(Some(_)) => return,
                Ok(None) => thread::sleep(Duration::from_millis(25)),
                Err(_) => break,
            }
        }
        unsafe {
            libc::kill(process_group, libc::SIGKILL);
        }
        let _ = self.child.wait();
    }
}

impl Drop for OwnedBackend {
    fn drop(&mut self) {
        self.terminate();
    }
}

fn parse_startup(
    stdout: impl io::Read + Send + 'static,
) -> mpsc::Receiver<Result<StartupContract, String>> {
    let (sender, receiver) = mpsc::channel();
    thread::spawn(move || {
        let mut last_line = String::new();
        for line in BufReader::new(stdout).lines() {
            match line {
                Ok(line) => {
                    last_line = line.clone();
                    if let Ok(contract) = serde_json::from_str::<StartupContract>(&line) {
                        let result = contract.validate().map_err(|error| error.to_string());
                        let _ = sender.send(result);
                        return;
                    }
                }
                Err(error) => {
                    let _ = sender.send(Err(format!("kunde inte läsa startup-kontrakt: {error}")));
                    return;
                }
            }
        }
        let _ = sender.send(Err(format!(
            "Python avslutade utan startup-kontrakt; sista rad: {last_line:?}"
        )));
    });
    receiver
}

struct DataLayout {
    data_root: PathBuf,
    backup_root: PathBuf,
    staging_root: PathBuf,
    log_file: PathBuf,
}

fn prepare_data_dirs(app_data_dir: &Path) -> Result<DataLayout, BoxError> {
    let log_dir = app_data_dir.join("logs");
    let layout = DataLayout {
        data_root: app_data_dir.join("data"),
        backup_root: app_data_dir.join("backups"),
        staging_root: app_data_dir.join("restore-staging"),
        log_file: log_dir.join("backend.log"),
    };
    for directory in [
        app_data_dir,
        &layout.data_root,
        &layout.backup_root,
        &layout.staging_root,
        &log_dir,
    ] {
        fs::create_dir_all(directory)?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(directory, fs::Permissions::from_mode(0o700))?;
        }
    }
    // Launched from the application menu there is no terminal to inherit, so
    // the backend's diagnostics would otherwise go nowhere.  Keep exactly one
    // previous run alongside the current one: enough to explain the crash the
    // user just saw, without growing without bound.
    let previous = layout.log_file.with_extension("log.1");
    let _ = fs::remove_file(&previous);
    let _ = fs::rename(&layout.log_file, &previous);
    Ok(layout)
}

/// Copy the backend's stderr to both the log file and our own stderr.
fn tee_backend_stderr(stderr: impl io::Read + Send + 'static, log_file: PathBuf) {
    thread::spawn(move || {
        let mut sink = fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&log_file)
            .ok();
        #[cfg(unix)]
        if let Some(handle) = &sink {
            use std::os::unix::fs::PermissionsExt;
            let _ = handle.set_permissions(fs::Permissions::from_mode(0o600));
        }
        for line in BufReader::new(stderr).lines() {
            let Ok(line) = line else { break };
            eprintln!("{line}");
            if let Some(handle) = sink.as_mut() {
                use std::io::Write;
                let _ = writeln!(handle, "{line}");
            }
        }
    });
}

fn spawn_backend(runtime: &RuntimeLayout, data: &DataLayout) -> Result<OwnedBackend, BoxError> {
    let mut command = Command::new(&runtime.python);
    command
        .current_dir(&runtime.backend_dir)
        // -E ignores ambient PYTHON* variables (PYTHONPATH/PYTHONHOME cannot
        // be used to shadow a bundled module), -s drops the user site
        // directory, -B keeps a read-only installation from attempting
        // bytecode writes.
        .args(["-E", "-s", "-B", "-m", "app.desktop", "--dist"])
        .arg(&runtime.dist)
        .arg("--data-root")
        .arg(&data.data_root)
        .arg("--backup-root")
        .arg(&data.backup_root)
        .arg("--staging-root")
        .arg(&data.staging_root)
        // Generation configuration belongs to the application's own config
        // file, never to whatever happened to be exported in this shell.
        .env_remove("ANTHROPIC_API_KEY")
        .env_remove("BRF_LLM")
        .env_remove("BRF_LLM_BASE_URL")
        .env_remove("BRF_LLM_MODEL")
        .env_remove("BRF_LLM_API_KEY")
        .env_remove("BRF_MODE")
        .env_remove("BRF_DATA_ROOT")
        .env("BRF_EMBEDDER", "model2vec")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    if let Some(weights) = &runtime.model2vec {
        command.arg("--model2vec").arg(weights);
    }

    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        unsafe {
            command.pre_exec(|| {
                #[cfg(target_os = "linux")]
                {
                    let parent = libc::getppid();
                    if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGTERM) == -1 {
                        return Err(io::Error::last_os_error());
                    }
                    // Close the small race where the parent could die before
                    // PR_SET_PDEATHSIG was installed.
                    if parent == 1 || libc::getppid() != parent {
                        return Err(io::Error::other("skalet avslutades under backendstart"));
                    }
                }
                if libc::setpgid(0, 0) == -1 {
                    Err(io::Error::last_os_error())
                } else {
                    Ok(())
                }
            });
        }
    }

    let mut child = command.spawn().map_err(|error| {
        format!(
            "kunde inte starta {}: {error}",
            runtime.python.display()
        )
    })?;
    if let Some(stderr) = child.stderr.take() {
        tee_backend_stderr(stderr, data.log_file.clone());
    }
    let stdout = child
        .stdout
        .take()
        .ok_or("Python-barnet saknar pipad stdout")?;
    let startup = parse_startup(stdout);
    match startup.recv_timeout(STARTUP_TIMEOUT) {
        Ok(Ok(contract)) => {
            // Preserve the exact contract on the shell's stdout for smoke
            // tests and operations without introducing a second JSON schema.
            println!("{}", serde_json::to_string(&contract)?);
            Ok(OwnedBackend { child, contract })
        }
        Ok(Err(error)) => {
            OwnedBackend::not_ready(child).terminate();
            Err(error.into())
        }
        Err(mpsc::RecvTimeoutError::Timeout) => {
            OwnedBackend::not_ready(child).terminate();
            Err(format!(
                "Python blev inte redo inom {} sekunder",
                STARTUP_TIMEOUT.as_secs()
            )
            .into())
        }
        Err(mpsc::RecvTimeoutError::Disconnected) => {
            OwnedBackend::not_ready(child).terminate();
            Err("startup-kanalen stängdes innan readiness".into())
        }
    }
}

fn same_origin(candidate: &tauri::Url, contract: &StartupContract) -> bool {
    candidate.scheme() == "http"
        && candidate.host_str() == Some("127.0.0.1")
        && candidate.port() == Some(contract.port)
}

// ---------------------------------------------------------------------------
// Window geometry
// ---------------------------------------------------------------------------

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq)]
struct WindowGeometry {
    width: f64,
    height: f64,
}

impl Default for WindowGeometry {
    fn default() -> Self {
        WindowGeometry {
            width: DEFAULT_WIDTH,
            height: DEFAULT_HEIGHT,
        }
    }
}

impl WindowGeometry {
    /// Clamp to something a compositor can actually show.  A geometry file
    /// written on a large screen must not open an unusable window on a small
    /// one, a truncated write must not open a 0×0 window, and a corrupt
    /// non-finite value falls back to the default size rather than to the
    /// smallest legal one.
    fn sanitized(self) -> Self {
        if !self.width.is_finite() || !self.height.is_finite() {
            return WindowGeometry::default();
        }
        WindowGeometry {
            width: self.width.clamp(MIN_WIDTH, 7680.0),
            height: self.height.clamp(MIN_HEIGHT, 4320.0),
        }
    }
}

fn geometry_path(app: &AppHandle) -> Option<PathBuf> {
    app.path().app_config_dir().ok().map(|dir| dir.join("window.json"))
}

fn load_geometry(app: &AppHandle) -> WindowGeometry {
    geometry_path(app)
        .and_then(|path| fs::read_to_string(path).ok())
        .and_then(|raw| serde_json::from_str::<WindowGeometry>(&raw).ok())
        .unwrap_or_default()
        .sanitized()
}

fn save_geometry(app: &AppHandle) {
    let Some(window) = app.get_webview_window("main") else {
        return;
    };
    let (Ok(size), Ok(scale)) = (window.inner_size(), window.scale_factor()) else {
        return;
    };
    let logical = size.to_logical::<f64>(scale);
    let geometry = WindowGeometry {
        width: logical.width,
        height: logical.height,
    }
    .sanitized();
    if let Some(path) = geometry_path(app) {
        if let Some(parent) = path.parent() {
            let _ = fs::create_dir_all(parent);
        }
        if let Ok(raw) = serde_json::to_string(&geometry) {
            let _ = fs::write(path, raw);
        }
    }
}

// ---------------------------------------------------------------------------
// Failure surface
// ---------------------------------------------------------------------------

/// Open the bundled, offline failure window.
///
/// This is deliberately a local Tauri asset rather than a native dialog: it
/// needs no plugin, so the shell keeps an empty capability set and the remote
/// HTTP origin gains no IPC surface.  The detail text is injected from Rust,
/// never fetched or evaluated.
fn show_failure(app: &AppHandle, headline: &str, detail: &str) {
    let payload = serde_json::json!({ "headline": headline, "detail": detail }).to_string();
    let script = format!("globalThis.__BRFV2_FAILURE__ = {payload};");
    let existing = app.get_webview_window("failure");
    if let Some(window) = existing {
        let _ = window.set_focus();
        return;
    }
    let built = WebviewWindowBuilder::new(app, "failure", WebviewUrl::App("index.html".into()))
        .title("Träff — kunde inte starta")
        .inner_size(720.0, 520.0)
        .min_inner_size(520.0, 380.0)
        .resizable(true)
        .initialization_script(&script)
        .on_new_window(|_, _| NewWindowResponse::Deny)
        .build();
    if let Err(error) = built {
        eprintln!("desktop failure window could not be shown: {error}");
        eprintln!("{headline}: {detail}");
    }
}

fn describe_exit(status: ExitStatus) -> String {
    #[cfg(unix)]
    {
        use std::os::unix::process::ExitStatusExt;
        if let Some(signal) = status.signal() {
            return format!("avslutades av signal {signal}");
        }
    }
    match status.code() {
        Some(code) => format!("avslutades med kod {code}"),
        None => "avslutades utan statuskod".to_string(),
    }
}

/// Watch the owned backend and react to the two ways it can end on its own.
fn supervise(
    app: AppHandle,
    backend: Arc<Mutex<Option<OwnedBackend>>>,
    shutting_down: Arc<AtomicBool>,
    log_file: PathBuf,
) {
    thread::spawn(move || loop {
        thread::sleep(SUPERVISOR_INTERVAL);
        if shutting_down.load(Ordering::SeqCst) {
            return;
        }
        let status = {
            let Ok(mut guard) = backend.lock() else {
                return;
            };
            match guard.as_mut() {
                Some(owned) => match owned.child.try_wait() {
                    Ok(Some(status)) => {
                        guard.take();
                        status
                    }
                    Ok(None) => continue,
                    Err(_) => return,
                },
                None => return,
            }
        };

        if shutting_down.load(Ordering::SeqCst) {
            return;
        }

        if status.code() == Some(RESTART_EXIT_CODE) {
            // A staged restore was applied on request; the swap itself happens
            // at the next start, before any store is opened.
            shutting_down.store(true, Ordering::SeqCst);
            let handle = app.clone();
            let _ = app.run_on_main_thread(move || {
                save_geometry(&handle);
                handle.restart();
            });
            return;
        }

        shutting_down.store(true, Ordering::SeqCst);
        let detail = format!(
            "Bakgrundstjänsten {}. Inga data har gått förlorade — dina dokument och \
             inställningar ligger kvar lokalt. Stäng fönstret och starta Träff igen.\n\n\
             Teknisk logg: {}",
            describe_exit(status),
            log_file.display()
        );
        let handle = app.clone();
        let _ = app.run_on_main_thread(move || {
            if let Some(window) = handle.get_webview_window("main") {
                let _ = window.close();
            }
            show_failure(&handle, "Applikationen tappade sin bakgrundstjänst", &detail);
        });
        return;
    });
}

fn cleanup(shared: &Arc<Mutex<Option<OwnedBackend>>>) {
    if let Ok(mut guard) = shared.lock() {
        if let Some(mut owned) = guard.take() {
            owned.terminate();
        }
    }
}

// ---------------------------------------------------------------------------
// Application
// ---------------------------------------------------------------------------

fn run() -> Result<(), BoxError> {
    let backend = Arc::new(Mutex::new(None::<OwnedBackend>));
    let shutting_down = Arc::new(AtomicBool::new(false));
    let setup_backend = Arc::clone(&backend);
    let setup_shutdown = Arc::clone(&shutting_down);

    let app = tauri::Builder::default()
        .setup(move |app| {
            let handle = app.handle().clone();
            let started = start_product(&handle, &setup_backend, &setup_shutdown);
            if let Err(error) = started {
                // A failed start is a normal, explainable state for an
                // installed application — never a silent exit to a terminal
                // nobody is watching.
                show_failure(
                    &handle,
                    "Träff kunde inte starta",
                    &error.to_string(),
                );
            }
            Ok(())
        })
        .build(tauri::generate_context!())?;

    let event_backend = Arc::clone(&backend);
    let event_shutdown = Arc::clone(&shutting_down);
    app.run(move |handle, event| {
        if matches!(event, RunEvent::ExitRequested { .. } | RunEvent::Exit) {
            if !event_shutdown.swap(true, Ordering::SeqCst) {
                save_geometry(handle);
            }
            cleanup(&event_backend);
        }
    });
    cleanup(&backend);
    Ok(())
}

fn start_product(
    app: &AppHandle,
    backend: &Arc<Mutex<Option<OwnedBackend>>>,
    shutting_down: &Arc<AtomicBool>,
) -> Result<(), BoxError> {
    let resource_dir = app.path().resource_dir().ok();
    let runtime = resolve_runtime(resource_dir.as_deref())?;
    let data = prepare_data_dirs(&app.path().app_data_dir()?)?;

    let owned = spawn_backend(&runtime, &data)?;
    let contract = owned.contract.clone();
    let url: tauri::Url = format!("{}/brfv2/", contract.origin).parse()?;
    let navigation_contract = contract.clone();

    *backend
        .lock()
        .map_err(|_| "backend process lock poisoned")? = Some(owned);

    let geometry = load_geometry(app);
    WebviewWindowBuilder::new(app, "main", WebviewUrl::External(url))
        .title("Träff")
        .inner_size(geometry.width, geometry.height)
        .min_inner_size(MIN_WIDTH, MIN_HEIGHT)
        .resizable(true)
        .on_navigation(move |candidate| same_origin(candidate, &navigation_contract))
        .on_new_window(|_, _| NewWindowResponse::Deny)
        .build()?;

    supervise(
        app.clone(),
        Arc::clone(backend),
        Arc::clone(shutting_down),
        data.log_file.clone(),
    );
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("desktop startup failed: {error}");
        std::process::exit(1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn valid_contract(port: u16) -> StartupContract {
        StartupContract {
            schema: STARTUP_SCHEMA.into(),
            status: "ready".into(),
            host: "127.0.0.1".into(),
            port,
            origin: format!("http://127.0.0.1:{port}"),
        }
    }

    #[test]
    fn startup_contract_accepts_only_exact_random_loopback_origin() {
        let valid = valid_contract(43123).validate().unwrap();

        assert!(same_origin(
            &"http://127.0.0.1:43123/brfv2/".parse().unwrap(),
            &valid
        ));
        assert!(same_origin(
            &"http://127.0.0.1:43123/api/health".parse().unwrap(),
            &valid
        ));
        assert!(!same_origin(
            &"http://localhost:43123/brfv2/".parse().unwrap(),
            &valid
        ));
        assert!(!same_origin(
            &"http://127.0.0.1:8787/brfv2/".parse().unwrap(),
            &valid
        ));
        assert!(!same_origin(
            &"https://example.com/".parse().unwrap(),
            &valid
        ));
    }

    #[test]
    fn startup_contract_rejects_origin_port_mismatch() {
        let mut invalid = valid_contract(43123);
        invalid.origin = "http://127.0.0.1:5173".into();
        assert!(invalid.validate().is_err());

        let mut not_ready = valid_contract(43123);
        not_ready.status = "starting".into();
        assert!(not_ready.validate().is_err());

        let mut off_host = valid_contract(43123);
        off_host.host = "0.0.0.0".into();
        off_host.origin = "http://0.0.0.0:43123".into();
        assert!(off_host.validate().is_err());
    }

    #[test]
    fn window_geometry_is_clamped_to_something_showable() {
        let restored = WindowGeometry {
            width: 1200.0,
            height: 800.0,
        }
        .sanitized();
        assert_eq!(restored.width, 1200.0);
        assert_eq!(restored.height, 800.0);

        let collapsed = WindowGeometry {
            width: 0.0,
            height: -4.0,
        }
        .sanitized();
        assert_eq!(collapsed.width, MIN_WIDTH);
        assert_eq!(collapsed.height, MIN_HEIGHT);

        let corrupt = WindowGeometry {
            width: f64::NAN,
            height: f64::INFINITY,
        }
        .sanitized();
        assert_eq!(corrupt, WindowGeometry::default());

        let oversized = WindowGeometry {
            width: 99_000.0,
            height: 99_000.0,
        }
        .sanitized();
        assert_eq!(oversized.width, 7680.0);
        assert_eq!(oversized.height, 4320.0);
    }

    #[test]
    fn packaged_layout_requires_every_part_of_the_bundle() {
        let temp = std::env::temp_dir().join(format!("brfv2-layout-{}", std::process::id()));
        let _ = fs::remove_dir_all(&temp);
        let runtime = temp.join("runtime");
        fs::create_dir_all(runtime.join("python/bin")).unwrap();
        fs::create_dir_all(runtime.join("backend/app")).unwrap();
        fs::write(runtime.join("python/bin/python3"), b"#!/bin/false\n").unwrap();
        fs::write(runtime.join("backend/app/desktop.py"), b"").unwrap();

        // No built UI yet: an API-only shell must not be considered packaged.
        assert!(packaged_layout(&temp).is_none());

        fs::create_dir_all(temp.join("ui")).unwrap();
        fs::write(temp.join("ui/index.html"), b"<!doctype html>").unwrap();
        // Still incomplete: without the bundled weights, model2vec would fetch
        // them from huggingface.co on first use.
        assert!(packaged_layout(&temp).is_none());

        fs::create_dir_all(runtime.join("models/potion-multilingual-128M")).unwrap();
        let layout = packaged_layout(&temp).expect("complete bundle");
        assert!(layout.packaged);
        assert_eq!(
            layout.model2vec,
            Some(runtime.join("models/potion-multilingual-128M"))
        );

        let _ = fs::remove_dir_all(&temp);
    }

    #[test]
    fn checkout_layout_uses_the_staged_weights_when_they_exist() {
        let temp = std::env::temp_dir().join(format!("brfv2-checkout-{}", std::process::id()));
        let _ = fs::remove_dir_all(&temp);
        fs::create_dir_all(&temp).unwrap();

        // Before `make desktop-runtime`: nothing to point at, and the backend
        // resolves the embedder the way a plain development run always has.
        assert_eq!(checkout_layout(&temp).model2vec, None);

        let staged = temp.join("src-tauri/runtime/models/potion-multilingual-128M");
        fs::create_dir_all(&staged).unwrap();
        let layout = checkout_layout(&temp);
        assert!(!layout.packaged);
        assert_eq!(layout.model2vec, Some(staged));

        let _ = fs::remove_dir_all(&temp);
    }
}
