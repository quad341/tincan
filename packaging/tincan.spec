Name:           tincan
Version:        0.1.0
Release:        1%{?dist}
Summary:        iPhone message and notification bridge over Bluetooth
License:        MIT
URL:            https://github.com/quad341/tincan
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3-devel
BuildRequires:  python3-setuptools

# python3-pyside6 is available in the official Fedora 42+ repositories
# (package python3-pyside6 ≥ 6.5 provides PySide6 6.x).
# If building for older distros, enable RPM Fusion or the upstream COPR.
Requires:       python3 >= 3.10
Requires:       python3-pyside6 >= 6.5
Requires:       python3-dbus
Requires:       python3-gobject
Requires:       python3-vobject
Requires:       bluez >= 5
# bluez-obexd ships obexd on Fedora; on other distros the package may be
# called 'obexd' — adjust below if needed.
Requires:       bluez-obexd

%description
tincan mirrors iPhone messages and ANCS notifications to a Linux desktop
over Bluetooth (MAP + ANCS).

Requirements:
  - BlueZ with Experimental=true in /etc/bluetooth/main.conf
  - obexd running (systemctl start bluetooth-obexd)
  - iPhone paired via bluetoothctl

See README.md for step-by-step setup instructions.

%prep
%autosetup

%build
%py3_build

%install
%py3_install

# Desktop entry and icon
install -Dm644 packaging/tincan.desktop \
    %{buildroot}%{_datadir}/applications/tincan.desktop
install -Dm644 packaging/tincan.svg \
    %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/tincan.svg
install -Dm644 packaging/tincan-256.png \
    %{buildroot}%{_datadir}/icons/hicolor/256x256/apps/tincan.png
install -Dm644 packaging/tincan-48.png \
    %{buildroot}%{_datadir}/icons/hicolor/48x48/apps/tincan.png

%post
gtk-update-icon-cache %{_datadir}/icons/hicolor &>/dev/null || :
update-desktop-database &>/dev/null || :

%postun
gtk-update-icon-cache %{_datadir}/icons/hicolor &>/dev/null || :
update-desktop-database &>/dev/null || :

%files
%license LICENSE
%doc README.md
%{python3_sitelib}/tincan_gui/
%{python3_sitelib}/tincand/
%{python3_sitelib}/tincan*.dist-info/
%{_bindir}/tincan
%{_bindir}/tincand-mcp
%{_datadir}/applications/tincan.desktop
%{_datadir}/icons/hicolor/scalable/apps/tincan.svg
%{_datadir}/icons/hicolor/256x256/apps/tincan.png
%{_datadir}/icons/hicolor/48x48/apps/tincan.png

%changelog
* Sun Jun 07 2026 Jim Wordelman <james@wordelman.name> - 0.1.0-1
- Initial package
