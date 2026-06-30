#!/usr/bin/env python3
"""Clash subscription management and conversion."""

import base64
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import requests
import yaml


class SubscriptionError(Exception):
    """Subscription related errors."""
    pass


class Subscription:
    """Clash subscription manager."""

    def __init__(self, subscriptions_file: str):
        """
        Initialize subscription manager.

        Args:
            subscriptions_file: Path to subscriptions.json
        """
        self.subscriptions_file = Path(subscriptions_file)
        self.data: Dict[str, Any] = self._load_subscriptions()

    def _load_subscriptions(self) -> Dict[str, Any]:
        """Load subscriptions from file."""
        if not self.subscriptions_file.exists():
            return {
                "version": "1.0",
                "active": None,
                "subscriptions": []
            }

        try:
            with open(self.subscriptions_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            raise SubscriptionError(f"Failed to load subscriptions: {e}")

    def _save_subscriptions(self):
        """Save subscriptions to file."""
        self.subscriptions_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.subscriptions_file, 'w') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            raise SubscriptionError(f"Failed to save subscriptions: {e}")

    def add(self, name: str, url: str, template: str = "balanced") -> Dict[str, Any]:
        """
        Add a new subscription.

        Args:
            name: Subscription name
            url: Subscription URL
            template: Template to use for conversion

        Returns:
            Subscription info dict
        """
        # Check if name already exists
        if any(sub['name'] == name for sub in self.data['subscriptions']):
            raise SubscriptionError(f"Subscription '{name}' already exists")

        sub = {
            "name": name,
            "url": url,
            "type": None,
            "template": template,
            "added_at": datetime.utcnow().isoformat() + "Z",
            "last_update": None,
            "node_count": 0,
            "status": "inactive"
        }

        self.data['subscriptions'].append(sub)
        self._save_subscriptions()
        return sub

    def remove(self, name: str):
        """Remove a subscription."""
        original_len = len(self.data['subscriptions'])
        self.data['subscriptions'] = [
            sub for sub in self.data['subscriptions'] if sub['name'] != name
        ]

        if len(self.data['subscriptions']) == original_len:
            raise SubscriptionError(f"Subscription '{name}' not found")

        if self.data['active'] == name:
            self.data['active'] = None

        self._save_subscriptions()

    def list(self) -> List[Dict[str, Any]]:
        """List all subscriptions."""
        return self.data['subscriptions']

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        """Get subscription by name."""
        for sub in self.data['subscriptions']:
            if sub['name'] == name:
                return sub
        return None

    def activate(self, name: str):
        """Activate a subscription."""
        if not self.get(name):
            raise SubscriptionError(f"Subscription '{name}' not found")

        # Deactivate all others
        for sub in self.data['subscriptions']:
            sub['status'] = 'active' if sub['name'] == name else 'inactive'

        self.data['active'] = name
        self._save_subscriptions()

    def update(self, name: str, template_dir: str, output_file: str) -> Tuple[str, int]:
        """
        Update subscription and generate config.

        Args:
            name: Subscription name
            template_dir: Directory containing templates
            output_file: Output config.yaml path

        Returns:
            Tuple of (subscription_type, node_count)
        """
        sub = self.get(name)
        if not sub:
            raise SubscriptionError(f"Subscription '{name}' not found")

        # Download subscription
        content = self._download(sub['url'])

        # Detect type
        sub_type = self._detect_type(content)
        sub['type'] = sub_type

        # Convert to Clash config
        if sub_type == 'yaml':
            config = yaml.safe_load(content)
            node_count = len(config.get('proxies', []))
        elif sub_type == 'base64':
            proxies, proxy_names = self._parse_base64(content)
            node_count = len(proxies)
            config = self._generate_config(
                proxies, proxy_names, sub['name'], sub['template'], template_dir
            )
        else:
            raise SubscriptionError(f"Unknown subscription type: {sub_type}")

        # Save config
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

        # Update subscription info
        sub['last_update'] = datetime.utcnow().isoformat() + "Z"
        sub['node_count'] = node_count
        self._save_subscriptions()

        return sub_type, node_count

    def _download(self, url: str) -> str:
        """Download subscription content."""
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            raise SubscriptionError(f"Failed to download subscription: {e}")

    def _detect_type(self, content: str) -> str:
        """
        Detect subscription type.

        Returns:
            'yaml', 'base64', or 'unknown'
        """
        # Try YAML first
        try:
            data = yaml.safe_load(content)
            if isinstance(data, dict) and 'proxies' in data:
                return 'yaml'
        except:
            pass

        # Check Base64
        if re.match(r'^[A-Za-z0-9+/=\s]+$', content.strip()):
            try:
                decoded = base64.b64decode(content.strip())
                decoded_str = decoded.decode('utf-8', errors='ignore')
                if any(proto in decoded_str for proto in ['vmess://', 'ss://', 'trojan://', 'ssr://']):
                    return 'base64'
            except:
                pass

        return 'unknown'

    def _parse_base64(self, content: str) -> Tuple[List[Dict], List[str]]:
        """
        Parse Base64 encoded subscription.

        Returns:
            Tuple of (proxies list, proxy names list)
        """
        decoded = base64.b64decode(content.strip()).decode('utf-8')
        lines = [line.strip() for line in decoded.split('\n') if line.strip()]

        proxies = []
        proxy_names = []

        for line in lines:
            if line.startswith('vmess://'):
                proxy = self._parse_vmess(line)
            elif line.startswith('ss://'):
                proxy = self._parse_shadowsocks(line)
            elif line.startswith('trojan://'):
                proxy = self._parse_trojan(line)
            else:
                continue

            if proxy:
                proxies.append(proxy)
                proxy_names.append(f"      - \"{proxy['name']}\"")

        return proxies, proxy_names

    def _parse_vmess(self, uri: str) -> Optional[Dict]:
        """Parse vmess:// URI."""
        try:
            encoded = uri.replace('vmess://', '')
            decoded = base64.b64decode(encoded).decode('utf-8')
            data = json.loads(decoded)

            return {
                'name': data.get('ps', 'VMess'),
                'type': 'vmess',
                'server': data.get('add'),
                'port': int(data.get('port', 443)),
                'uuid': data.get('id'),
                'alterId': int(data.get('aid', 0)),
                'cipher': data.get('scy', 'auto'),
                'network': data.get('net', 'tcp'),
                'tls': data.get('tls') == 'tls',
            }
        except:
            return None

    def _parse_shadowsocks(self, uri: str) -> Optional[Dict]:
        """Parse ss:// URI."""
        try:
            uri = uri.replace('ss://', '')
            if '#' in uri:
                uri, name = uri.split('#', 1)
            else:
                name = 'Shadowsocks'

            decoded = base64.b64decode(uri).decode('utf-8')
            method, rest = decoded.split(':', 1)
            password, server_port = rest.rsplit('@', 1)
            server, port = server_port.split(':', 1)

            return {
                'name': name,
                'type': 'ss',
                'server': server,
                'port': int(port),
                'cipher': method,
                'password': password,
            }
        except:
            return None

    def _parse_trojan(self, uri: str) -> Optional[Dict]:
        """Parse trojan:// URI."""
        try:
            parsed = urlparse(uri)
            name = parse_qs(parsed.query).get('sni', ['Trojan'])[0] if parsed.query else 'Trojan'

            return {
                'name': name,
                'type': 'trojan',
                'server': parsed.hostname,
                'port': parsed.port or 443,
                'password': parsed.username,
                'sni': parsed.hostname,
            }
        except:
            return None

    def _generate_config(
        self,
        proxies: List[Dict],
        proxy_names: List[str],
        sub_name: str,
        template_name: str,
        template_dir: str
    ) -> Dict:
        """Generate Clash config from template."""
        template_path = Path(template_dir) / f"{template_name}.yaml"
        if not template_path.exists():
            raise SubscriptionError(f"Template not found: {template_path}")

        with open(template_path, 'r') as f:
            template_content = f.read()

        # Format proxies as YAML
        proxies_yaml = yaml.dump(proxies, default_flow_style=False, allow_unicode=True)
        # Remove the leading list marker to get proper indentation
        proxies_yaml = '\n'.join('  ' + line if line and not line.startswith('-') else line
                                 for line in proxies_yaml.split('\n'))

        # Replace placeholders
        config_content = template_content.replace('{{proxies}}', proxies_yaml.strip())
        config_content = config_content.replace('{{proxy_names}}', '\n'.join(proxy_names))
        config_content = config_content.replace('{{generated_time}}', datetime.now().isoformat())
        config_content = config_content.replace('{{subscription_name}}', sub_name)

        return yaml.safe_load(config_content)
