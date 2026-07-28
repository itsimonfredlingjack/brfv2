# RPM spec for the BRF Dokument-AI Fedora desktop delivery.
#
# The package is assembled by ops/package-desktop.sh, which stages a complete
# buildroot first; this spec only describes and packs it. Everything below that
# looks like a workaround is one, and each is load-bearing:
#
#   AutoReqProv: no   The bundle carries its own CPython and its own compiled
#                     extension modules. rpm's automatic dependency generator
#                     would turn every bundled .so into a system requirement
#                     (down to libpython3.12.so.1.0, which no Fedora package
#                     provides), making the package uninstallable. The real
#                     external dependencies are listed by hand below.
#   disabled brp      The same bundled tree must not be stripped, have its
#   macros            shebangs rewritten, or be byte-compiled by Fedora's
#                     Python macros. What ships has to be exactly what the
#                     acceptance run exercised.

%global appname     BRF Dokument-AI
%global binname     brfv2-desktop
%global _binary_payload w3.zstdio

%global debug_package %{nil}
%define __brp_strip %{nil}
%define __brp_strip_static_archive %{nil}
%define __brp_strip_comment_note %{nil}
%define __brp_mangle_shebangs %{nil}
%define __brp_check_rpaths %{nil}
%define __brp_python_bytecompile %{nil}
%define __brp_python_hardlink %{nil}

Name:           brf-dokument-ai
Version:        %{brfversion}
Release:        1%{?dist}
Summary:        Grundade svar ur bostadsrättsföreningens egna dokument
License:        Proprietary
URL:            https://github.com/simonfredlingjack/brfv2
BuildArch:      x86_64
AutoReqProv:    no

Requires:       webkit2gtk4.1
Requires:       gtk3
Requires:       tesseract
Requires:       tesseract-langpack-swe

%description
BRF Dokument-AI besvarar frågor om en bostadsrättsförenings egna dokument och
visar alltid exakt var i vilken PDF svaret står. Frågor utan stöd i dokumenten
besvaras inte — de avvisas.

Dokumentbehandling, index, sökvektorer och lagring körs lokalt på datorn.
Textgenerering sker mot den självhostade modelltjänst som användaren själv
anger i applikationen; någon annan extern tjänst kontaktas inte.

Applikationens data ligger under ~/.local/share/se.brfdokumentai.desktop och
påverkas inte av av- eller ominstallation.

%prep

%build

%install
# ops/package-desktop.sh stages a complete tree; this only moves it into the
# buildroot rpmbuild chose. -a preserves the permissions and the internal
# relative symlinks of the bundled CPython.
cp -a %{stagedroot}/. %{buildroot}/

%files
%attr(0755, root, root) %{_bindir}/%{binname}
# Quoted: the product name contains a space, and %files splits on whitespace.
"%{_prefix}/lib/%{appname}"
"%{_datadir}/applications/%{appname}.desktop"
%{_datadir}/icons/hicolor/32x32/apps/%{binname}.png
%{_datadir}/icons/hicolor/128x128/apps/%{binname}.png
%{_datadir}/icons/hicolor/256x256/apps/%{binname}.png

%changelog
* Tue Jul 28 2026 BRF Dokument-AI <noreply@example.com> - 0.2.0-1
- Första distributionsbara skrivbordsleveransen: paketerad Python-körmiljö,
  medföljande embeddervikter, förstagångskonfiguration i appen, säkerhets-
  kopiering och återställning.
