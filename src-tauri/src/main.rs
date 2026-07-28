use serde::{Deserialize, Serialize};
use std::{
    env, fs,
    io::{self, BufRead, BufReader},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{mpsc, Arc, Mutex},
    thread,
    time::{Duration, Instant},
};
use tauri::{webview::NewWindowResponse, Manager, RunEvent, WebviewUrl, WebviewWindowBuilder};

const STARTUP_SCHEMA: &str = "brfv2-desktop-startup/v1";
const STARTUP_TIMEOUT: Duration = Duration::from_secs(45);
const SHUTDOWN_GRACE: Duration = Duration::from_secs(3);

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

struct OwnedBackend {
    child: Child,
    contract: StartupContract,
}

impl OwnedBackend {
    fn terminate(&mut self) {
        if matches!(self.child.try_wait(), Ok(Some(_))) {
            return;
        }

        let process_group = -(self.child.id() as i32);
        // The Python process starts its own group.  Signal the entire owned
        // group so a future adapter subprocess cannot outlive the Tauri app.
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

fn find_repo_root() -> Result<PathBuf, BoxError> {
    if let Some(explicit) = env::var_os("BRFV2_REPO_ROOT") {
        let path = PathBuf::from(explicit);
        if is_repo_root(&path) {
            return Ok(path.canonicalize()?);
        }
        return Err("BRFV2_REPO_ROOT saknar backendmiljö eller byggd frontend".into());
    }

    let mut roots = Vec::new();
    roots.extend(candidate_and_ancestors(env::current_dir()?));
    if let Ok(executable) = env::current_exe() {
        if let Some(parent) = executable.parent() {
            roots.extend(candidate_and_ancestors(parent.to_path_buf()));
        }
    }
    roots
        .into_iter()
        .find(|candidate| is_repo_root(candidate))
        .map(|candidate| candidate.canonicalize())
        .transpose()?
        .ok_or_else(|| {
            "kunde inte hitta reporoten; kör från checkouten eller sätt BRFV2_REPO_ROOT".into()
        })
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
            "Python avslutade stdout utan startup-kontrakt; sista rad: {last_line:?}"
        )));
    });
    receiver
}

fn spawn_backend(repo_root: &Path, data_root: &Path) -> Result<OwnedBackend, BoxError> {
    let python = repo_root.join("backend/.venv/bin/python");
    let dist = repo_root.join("brfv2-mockup/dist");
    let mut command = Command::new(&python);
    command
        .current_dir(repo_root.join("backend"))
        .args(["-m", "app.desktop", "--dist"])
        .arg(&dist)
        .arg("--data-root")
        .arg(data_root)
        .arg("--seed-demo")
        .env(
            "BRF_LLM",
            env::var_os("BRF_LLM").unwrap_or_else(|| "scripted".into()),
        )
        .env(
            "BRF_EMBEDDER",
            env::var_os("BRF_EMBEDDER").unwrap_or_else(|| "hashed".into()),
        )
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit());

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
                        return Err(io::Error::other(
                            "Tauri-föräldern avslutades under backendstart",
                        ));
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

    let mut child = command.spawn()?;
    let stdout = child
        .stdout
        .take()
        .ok_or("Python-barnet saknar pipad stdout")?;
    let startup = parse_startup(stdout);
    match startup.recv_timeout(STARTUP_TIMEOUT) {
        Ok(Ok(contract)) => {
            // Preserve the exact contract on Tauri's stdout for smoke tests
            // and operations without introducing a second JSON schema.
            println!("{}", serde_json::to_string(&contract)?);
            Ok(OwnedBackend { child, contract })
        }
        Ok(Err(error)) => {
            let mut owned = OwnedBackend {
                child,
                contract: StartupContract {
                    schema: STARTUP_SCHEMA.into(),
                    status: "not-ready".into(),
                    host: "127.0.0.1".into(),
                    port: 1,
                    origin: "http://127.0.0.1:1".into(),
                },
            };
            owned.terminate();
            Err(error.into())
        }
        Err(mpsc::RecvTimeoutError::Timeout) => {
            let mut owned = OwnedBackend {
                child,
                contract: StartupContract {
                    schema: STARTUP_SCHEMA.into(),
                    status: "not-ready".into(),
                    host: "127.0.0.1".into(),
                    port: 1,
                    origin: "http://127.0.0.1:1".into(),
                },
            };
            owned.terminate();
            Err(format!(
                "Python blev inte redo inom {} sekunder",
                STARTUP_TIMEOUT.as_secs()
            )
            .into())
        }
        Err(mpsc::RecvTimeoutError::Disconnected) => {
            let mut owned = OwnedBackend {
                child,
                contract: StartupContract {
                    schema: STARTUP_SCHEMA.into(),
                    status: "not-ready".into(),
                    host: "127.0.0.1".into(),
                    port: 1,
                    origin: "http://127.0.0.1:1".into(),
                },
            };
            owned.terminate();
            Err("startup-kanalen stängdes innan readiness".into())
        }
    }
}

fn same_origin(candidate: &tauri::Url, contract: &StartupContract) -> bool {
    candidate.scheme() == "http"
        && candidate.host_str() == Some("127.0.0.1")
        && candidate.port() == Some(contract.port)
}

fn cleanup(shared: &Arc<Mutex<Option<OwnedBackend>>>) {
    if let Ok(mut guard) = shared.lock() {
        if let Some(mut backend) = guard.take() {
            backend.terminate();
        }
    }
}

fn run() -> Result<(), BoxError> {
    let backend = Arc::new(Mutex::new(None::<OwnedBackend>));
    let setup_backend = Arc::clone(&backend);

    let app = tauri::Builder::default()
        .setup(move |app| {
            let repo_root = find_repo_root().map_err(|error| error.to_string())?;
            let data_root = app.path().app_data_dir()?.join("data");
            fs::create_dir_all(&data_root)?;
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                fs::set_permissions(&data_root, fs::Permissions::from_mode(0o700))?;
            }

            let owned = spawn_backend(&repo_root, &data_root).map_err(|error| error.to_string())?;
            let contract = owned.contract.clone();
            let url: tauri::Url = format!("{}/brfv2/", contract.origin).parse()?;
            let navigation_contract = contract.clone();

            *setup_backend
                .lock()
                .map_err(|_| "backend process lock poisoned")? = Some(owned);

            WebviewWindowBuilder::new(app, "main", WebviewUrl::External(url))
                .title("BRF Dokument-AI")
                .inner_size(1440.0, 920.0)
                .min_inner_size(780.0, 600.0)
                .resizable(true)
                .on_navigation(move |candidate| same_origin(candidate, &navigation_contract))
                .on_new_window(|_, _| NewWindowResponse::Deny)
                .build()?;
            Ok(())
        })
        .build(tauri::generate_context!())?;

    let event_backend = Arc::clone(&backend);
    app.run(move |_handle, event| {
        if matches!(event, RunEvent::ExitRequested { .. } | RunEvent::Exit) {
            cleanup(&event_backend);
        }
    });
    cleanup(&backend);
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

    #[test]
    fn startup_contract_accepts_only_exact_random_loopback_origin() {
        let valid = StartupContract {
            schema: STARTUP_SCHEMA.into(),
            status: "ready".into(),
            host: "127.0.0.1".into(),
            port: 43123,
            origin: "http://127.0.0.1:43123".into(),
        }
        .validate()
        .unwrap();

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
        let invalid = StartupContract {
            schema: STARTUP_SCHEMA.into(),
            status: "ready".into(),
            host: "127.0.0.1".into(),
            port: 43123,
            origin: "http://127.0.0.1:5173".into(),
        };
        assert!(invalid.validate().is_err());
    }
}
