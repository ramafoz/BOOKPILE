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
    override = read("fail2ban/jail.d/bookpile-observe.local")
    assert override.count("enabled = true") == 2
    for forbidden in ("<ip>", "<matches>", "nft", "iptables", "firewall"):
        assert forbidden not in action


def test_fail2ban_database_is_persistent() -> None:
    config = read("fail2ban/fail2ban.d/bookpile.local")
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


def test_deployment_does_not_activate_d6() -> None:
    deploy = read("deploy-staging.sh")
    assert "install-bookpile-edge-defence" not in deploy
    assert "fail2ban" not in deploy.lower()
