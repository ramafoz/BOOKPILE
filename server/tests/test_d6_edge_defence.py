from pathlib import Path
import json
import subprocess
import sys


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
    disable_block = installer.split("  --disable-observe)", 1)[1].split(
        "  --check)", 1
    )[0]
    assert disable_block.index("installation_started='true'") < disable_block.index(
        "check_host"
    )
    assert "emergency fail-open cleanup stopped Fail2ban" in installer
    assert "emergency cleanup could not fully verify" in installer
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


def test_real_health_jails_are_separate_and_disabled() -> None:
    config = read("fail2ban/jail.d/bookpile-health-enforce.conf")
    assert config.count("enabled = false") == 2
    assert "[bookpile-health-live-enforce]" in config
    assert "[bookpile-health-ready-enforce]" in config
    assert "action = bookpile-nftables-live" in config
    assert "action = bookpile-nftables-ready" in config
    assert "maxretry = 121" in config
    assert "maxretry = 31" in config
    assert config.count("findtime = 60") == 2
    assert config.count("bantime = 600") == 2

    live_switch = read("fail2ban/jail.d/zz-bookpile-live-enforce.local")
    ready_switch = read("fail2ban/jail.d/zz-bookpile-ready-enforce.local")
    assert "[bookpile-health-live-observe]" in live_switch
    assert "[bookpile-health-live-enforce]" in live_switch
    assert live_switch.count("enabled = true") == 1
    assert live_switch.count("enabled = false") == 1
    assert "ready" not in live_switch
    assert "[bookpile-health-ready-observe]" in ready_switch
    assert "[bookpile-health-ready-enforce]" in ready_switch
    assert ready_switch.count("enabled = true") == 1
    assert ready_switch.count("enabled = false") == 1
    assert "live" not in ready_switch


def test_real_actions_are_separate_bounded_and_privacy_safe() -> None:
    live = read("fail2ban/action.d/bookpile-nftables-live.conf")
    ready = read("fail2ban/action.d/bookpile-nftables-ready.conf")
    for action, policy in ((live, "live"), (ready, "ready")):
        assert "actionstart_on_demand = false" in action
        assert f"bookpile-edge-firewall ban {policy} <ip>" in action
        assert f"bookpile-edge-firewall unban {policy} <ip>" in action
        assert f"bookpile-edge-firewall flush {policy}" in action
        assert "event=temporary_ban " in action
        assert "event=temporary_ban_released " in action
        assert "<ip>" not in "\n".join(
            line for line in action.splitlines() if "/usr/bin/logger" in line
        )


def test_nftables_policy_cannot_match_ssh_or_internal_health() -> None:
    policy = read("nftables/bookpile-health-enforcement.nft")
    assert "table inet bookpile" in policy
    assert policy.count("set health_") == 2
    assert "health_live_ipv4" in policy
    assert "health_ready_ipv4" in policy
    assert policy.count("timeout 10m") == 2
    assert policy.count("type filter hook forward priority -10; policy accept;") == 1
    assert policy.count("ct original proto-dst { 80, 443 }") == 2
    assert policy.count(" drop comment ") == 2
    assert "22" not in policy
    assert "8100" not in policy
    assert "input" not in policy.lower()
    assert "output" not in policy.lower()


def _valid_nftables_document() -> dict[str, object]:
    def rule(comment: str, set_name: str) -> dict[str, object]:
        return {
            "rule": {
                "family": "inet",
                "table": "bookpile",
                "chain": "public_web_guard",
                "comment": comment,
                "expr": [
                    {
                        "match": {
                            "op": "==",
                            "left": {"meta": {"key": "l4proto"}},
                            "right": "tcp",
                        }
                    },
                    {
                        "match": {
                            "op": "==",
                            "left": {
                                "ct": {"key": "proto-dst", "dir": "original"}
                            },
                            "right": {"set": [80, 443]},
                        }
                    },
                    {
                        "match": {
                            "op": "==",
                            "left": {
                                "payload": {"protocol": "ip", "field": "saddr"}
                            },
                            "right": f"@{set_name}",
                        }
                    },
                    {"drop": None},
                ],
            }
        }

    return {
        "nftables": [
            {"metainfo": {"json_schema_version": 1}},
            {"table": {"family": "inet", "name": "bookpile"}},
            {
                "set": {
                    "family": "inet",
                    "table": "bookpile",
                    "name": "health_live_ipv4",
                    "type": "ipv4_addr",
                    "flags": ["timeout"],
                    "timeout": 600,
                }
            },
            {
                "set": {
                    "family": "inet",
                    "table": "bookpile",
                    "name": "health_ready_ipv4",
                    "type": "ipv4_addr",
                    "flags": ["timeout"],
                    "timeout": 600,
                }
            },
            {
                "chain": {
                    "family": "inet",
                    "table": "bookpile",
                    "name": "public_web_guard",
                    "type": "filter",
                    "hook": "forward",
                    "prio": -10,
                    "policy": "accept",
                }
            },
            rule("bookpile health live", "health_live_ipv4"),
            rule("bookpile health ready", "health_ready_ipv4"),
        ]
    }


def test_nftables_validator_accepts_only_the_reviewed_shape() -> None:
    validator = DEPLOY / "validate-bookpile-nftables.py"
    valid = _valid_nftables_document()
    completed = subprocess.run(
        [sys.executable, str(validator)],
        input=json.dumps(valid),
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(completed.stdout) == {
        "chain": "public_web_guard",
        "family": "inet",
        "policy_sets": ["health_live_ipv4", "health_ready_ipv4"],
        "rules": 2,
        "ssh_port_matched": False,
    }

    unsafe_documents = []
    extra_rule = json.loads(json.dumps(valid))
    extra_rule["nftables"].append(extra_rule["nftables"][-1])
    unsafe_documents.append(extra_rule)
    ssh_rule = json.loads(json.dumps(valid))
    ssh_rule["nftables"][-1]["rule"]["expr"][1]["match"]["right"] = {
        "set": [22, 443]
    }
    unsafe_documents.append(ssh_rule)
    input_chain = json.loads(json.dumps(valid))
    input_chain["nftables"][3 + 1]["chain"]["hook"] = "input"
    unsafe_documents.append(input_chain)
    extra_condition = json.loads(json.dumps(valid))
    extra_condition["nftables"][-1]["rule"]["expr"].insert(
        3,
        {
            "match": {
                "op": "==",
                "left": {"meta": {"key": "iifname"}},
                "right": "unexpected0",
            }
        },
    )
    unsafe_documents.append(extra_condition)

    for document in unsafe_documents:
        rejected = subprocess.run(
            [sys.executable, str(validator)],
            input=json.dumps(document),
            capture_output=True,
            text=True,
        )
        assert rejected.returncode == 1
        assert rejected.stdout == ""
        assert "PolicyValidationError" in rejected.stderr


def test_enforcement_installer_is_manual_idempotent_and_fail_open() -> None:
    installer = read("install-bookpile-edge-enforcement.sh")
    assert "STAGING-D6-ENFORCEMENT-POLICY" in installer
    assert "STAGING-D6-ENFORCEMENT-ENABLE" in installer
    for mode in (
        "--install-disabled",
        "--check-disabled",
        "--enable-live",
        "--enable-ready",
        "--disable-live",
        "--disable-ready",
        "--disable-all",
    ):
        assert mode in installer
    assert "assert_no_global_ipv6" in installer
    assert "Installed enforcement file differs from reviewed source" in installer
    assert "Enforcement switch differs from reviewed source" in installer
    assert "cleanup_failed_enable" in installer
    assert "emergency_disable_all" in installer
    assert 'assert_switch "$policy"' in installer
    assert 'assert_jails' in installer
    assert "nft delete table inet bookpile" in installer
    assert "systemctl disable --now fail2ban.service" in installer
    assert "ssh_port_matched\":false" in installer
    assert "install-bookpile-edge-defence.sh" in installer
    assert "deploy-staging.sh" not in installer

    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    assert "sudo unshare --net" in workflow
    assert "bookpile-health-enforcement.nft" in workflow
    assert "validate-bookpile-nftables.py" in workflow

    observation_installer = read("install-bookpile-edge-defence.sh")
    assert "--provenance-check" in observation_installer
    assert "bookpile-health-enforce.conf" in observation_installer
    assert "zz-bookpile-live-enforce.local" in observation_installer
    assert "zz-bookpile-ready-enforce.local" in observation_installer
    assert "bookpile-nftables-live.d" in observation_installer
    assert "bookpile-nftables-ready.d" in observation_installer
