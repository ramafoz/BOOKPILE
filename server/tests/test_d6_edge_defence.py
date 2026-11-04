from pathlib import Path


ROOT = Path(__file__).parents[2]
DEPLOY = ROOT / "server" / "deploy"


def read(relative: str) -> str:
    return (DEPLOY / relative).read_text(encoding="utf-8")


def test_health_jails_are_separate_disabled_and_exact() -> None:
    config = read("fail2ban/jail.d/bookpile-health.conf")
    assert config.count("enabled = false") == 2
    assert "[bookpile-health-live-observe]" in config
    assert "[bookpile-health-ready-observe]" in config
    assert "maxretry = 121" in config
    assert "maxretry = 31" in config
    assert config.count("findtime = 60") == 2
    assert config.count("bantime = 600") == 2


def test_observation_is_explicit_and_cannot_mutate_firewall() -> None:
    action = read("fail2ban/action.d/bookpile-observe.conf").lower()
    legacy_action = read("fail2ban/migrations/bookpile-observe-v1.conf").lower()
    override = read("fail2ban/jail.d/bookpile-observe.local")
    assert override.count("enabled = true") == 2
    for forbidden in ("<ip>", "<matches>", "nft", "iptables", "firewall"):
        assert forbidden not in action
    assert "event=would_temporarily_ban" in action
    assert "event=observation_released" in action
    assert "observation_expired" not in action
    assert "event=observation_expired" in legacy_action
    assert legacy_action.replace("observation_expired", "observation_released") == action

    packaged = read("fail2ban/jail.d/bookpile-disable-packaged.local")
    assert "[sshd]" in packaged
    assert "enabled = false" in packaged


def test_fail2ban_database_is_persistent() -> None:
    config = read("fail2ban/fail2ban.d/bookpile.local")
    assert "loglevel = ERROR" in config
    assert "loglevel = NOTICE" not in config
    assert "dbfile = /var/lib/fail2ban/fail2ban.sqlite3" in config
    assert "dbfile = none" not in config.lower()
    assert "dbfile = :memory:" not in config.lower()


def test_installation_is_manual_confirmed_and_ipv6_fail_closed() -> None:
    installer = read("install-bookpile-edge-defence.sh")
    assert "STAGING-D6-OBSERVE-INSTALL" in installer
    assert "ip -6 -o addr show scope global" in installer
    assert "validate-caddy-defensive-log.py" in installer
    assert "firewall_mutated\":false" in installer
    assert "nft list table inet bookpile" in installer
    assert "Fail2ban is already installed" in installer
    assert "systemctl mask --runtime fail2ban.service" in installer
    assert "assert_only_approved_jails" in installer
    assert installer.count("nft -j --stateless list ruleset") == 8
    assert "nft -j list ruleset" not in installer
    assert "cleanup_failed_installation" in installer
    assert "--resume-observe" in installer
    assert "--upgrade-observe" in installer
    assert "--enable-observe" in installer
    assert "assert_no_enabled_jails" in installer
    assert "assert_runtime_jail_count 2" in installer
    assert "assert_runtime_jail_count 0" in installer
    assert "fail2ban-client reload >/dev/null 2>&1" in installer
    assert "systemctl enable --now fail2ban.service" in installer
    assert "Expected no enabled jails" in installer
    assert "Firewall rules changed while enabling observation" in installer
    assert "Firewall rules changed while disabling observation" in installer
    assert "Firewall rules changed while upgrading observation" in installer
    assert "bookpile-observe-v1.conf" in installer
    assert "assert_managed_files_match" in installer
    assert "cmp --silent" in installer
    assert "non-regular, or a symlink" in installer
    assert "root:root 644" in installer
    assert "assert_no_unreviewed_overrides" in installer
    assert "Unreviewed Fail2ban .local override" in installer
    assert "dpkg --verify fail2ban" in installer
    assert "Unreviewed non-package jail configuration" in installer
    assert "dpkg-query -L fail2ban" in installer
    assert "local -a package_files=()" in installer
    assert '[[ "$file" == "$package_file" ]]' in installer
    assert "dpkg-query -S" not in installer
    assert "bookpile-health-live-observe|bookpile-health-ready-observe" not in installer
    assert "action.d/bookpile-observe.local" in installer
    assert "filter.d/bookpile-health-live.local" in installer
    assert "filter.d/bookpile-health-ready.local" in installer
    assert "action.d/bookpile-observe.d" in installer
    assert "filter.d/bookpile-health-live.d" in installer
    assert "filter.d/bookpile-health-ready.d" in installer
    assert "Unreviewed BOOKPILE component drop-in directory" in installer
    assert 'find "$CONFIG_ROOT/fail2ban.d"' in installer
    assert "configuration directory is missing, non-directory, or a symlink" in installer
    assert "root:root 755" in installer
    assert 'find "$CONFIG_ROOT" -type l -print -quit' in installer
    assert "Symlink is forbidden in the Fail2ban configuration tree" in installer
    assert "wait_for_server" in installer
    assert "seq 1 30" in installer


def test_deployment_does_not_activate_d6() -> None:
    deploy = read("deploy-staging.sh")
    assert "install-bookpile-edge-defence" not in deploy
    assert "fail2ban" not in deploy.lower()
