#!/usr/bin/env python3
"""Health check system for lab-remote-bootstrap."""

import json
import subprocess
import time
from typing import Dict, List, Optional, Tuple

import requests


class HealthCheck:
    """Health check system."""

    def __init__(self, config):
        """
        Initialize health checker.

        Args:
            config: Config instance
        """
        self.config = config

    def run_all(self, check_connectivity: bool = True) -> Dict:
        """
        Run all health checks.

        Args:
            check_connectivity: Whether to run connectivity tests

        Returns:
            Health check results dict
        """
        start_time = time.time()
        checks = []

        # Service checks
        checks.extend(self._check_services())

        # Port checks
        checks.extend(self._check_ports())

        # Connectivity checks
        if check_connectivity:
            checks.extend(self._check_connectivity())

        duration = time.time() - start_time

        passed = sum(1 for c in checks if c['status'] == 'pass')
        total = len(checks)

        return {
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'overall_status': 'healthy' if passed == total else 'unhealthy',
            'checks': checks,
            'summary': {
                'total': total,
                'passed': passed,
                'failed': total - passed,
                'duration_seconds': round(duration, 2)
            }
        }

    def _check_services(self) -> List[Dict]:
        """Check service status."""
        checks = []

        # Check Clash process
        clash_check = self._check_process('clash|mihomo|CrashCore', 'Clash')
        checks.append(clash_check)

        # Check AutoSSH process
        autossh_check = self._check_process('autossh', 'AutoSSH')
        checks.append(autossh_check)

        return checks

    def _check_process(self, pattern: str, service_name: str) -> Dict:
        """
        Check if process is running.

        Args:
            pattern: Regex pattern for process
            service_name: Human-readable service name

        Returns:
            Check result dict
        """
        try:
            result = subprocess.run(
                ['ps', 'aux'],
                capture_output=True,
                text=True,
                timeout=5
            )

            lines = [
                line for line in result.stdout.split('\n')
                if pattern in line and 'grep' not in line
            ]

            if lines:
                # Extract PID (second column)
                pid = lines[0].split()[1] if len(lines[0].split()) > 1 else 'unknown'
                return {
                    'category': 'service',
                    'name': f'{service_name.lower()}_process',
                    'status': 'pass',
                    'message': f'{service_name} process running (PID: {pid})',
                    'details': {'pid': pid}
                }
            else:
                return {
                    'category': 'service',
                    'name': f'{service_name.lower()}_process',
                    'status': 'fail',
                    'message': f'{service_name} process not running',
                    'details': {}
                }
        except Exception as e:
            return {
                'category': 'service',
                'name': f'{service_name.lower()}_process',
                'status': 'fail',
                'message': f'Failed to check {service_name} process: {e}',
                'details': {}
            }

    def _check_ports(self) -> List[Dict]:
        """Check port listening status."""
        checks = []

        ports = [
            (self.config.get('clash.http_port', 7890), 'http_proxy_port', 'HTTP proxy'),
            (self.config.get('clash.socks_port', 7891), 'socks_proxy_port', 'SOCKS proxy'),
            (self.config.get('clash.api_port', 9090), 'api_port', 'API'),
        ]

        for port, name, description in ports:
            check = self._check_port_listening(port, name, description)
            checks.append(check)

        return checks

    def _check_port_listening(self, port: int, name: str, description: str) -> Dict:
        """
        Check if port is listening.

        Args:
            port: Port number
            name: Check name
            description: Human-readable description

        Returns:
            Check result dict
        """
        try:
            # Try ss first (modern)
            result = subprocess.run(
                ['ss', '-tlnp'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0:
                # Fall back to netstat
                result = subprocess.run(
                    ['netstat', '-tlnp'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )

            if str(port) in result.stdout:
                return {
                    'category': 'port',
                    'name': name,
                    'status': 'pass',
                    'message': f'{description} port {port} listening',
                    'details': {'port': port}
                }
            else:
                return {
                    'category': 'port',
                    'name': name,
                    'status': 'fail',
                    'message': f'{description} port {port} not listening',
                    'details': {'port': port}
                }
        except Exception as e:
            return {
                'category': 'port',
                'name': name,
                'status': 'fail',
                'message': f'Failed to check port {port}: {e}',
                'details': {'port': port}
            }

    def _check_connectivity(self) -> List[Dict]:
        """Check connectivity."""
        checks = []

        # Check Clash API
        api_check = self._check_clash_api()
        checks.append(api_check)

        # Check proxy connectivity
        if api_check['status'] == 'pass':
            proxy_check = self._check_proxy_connectivity()
            checks.append(proxy_check)

        # Check reverse tunnel (if in remote context)
        # This would need SSH access, skipping for now

        return checks

    def _check_clash_api(self) -> Dict:
        """Check Clash API accessibility."""
        api_port = self.config.get('clash.api_port', 9090)
        url = f'http://127.0.0.1:{api_port}/version'

        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            data = response.json()

            version = data.get('version', 'unknown')
            return {
                'category': 'connectivity',
                'name': 'clash_api',
                'status': 'pass',
                'message': f'Clash API accessible (version: {version})',
                'details': {'version': version, 'url': url}
            }
        except requests.exceptions.ConnectionError:
            return {
                'category': 'connectivity',
                'name': 'clash_api',
                'status': 'fail',
                'message': f'Clash API not accessible at {url}',
                'details': {'url': url}
            }
        except Exception as e:
            return {
                'category': 'connectivity',
                'name': 'clash_api',
                'status': 'fail',
                'message': f'Failed to check Clash API: {e}',
                'details': {'url': url}
            }

    def _check_proxy_connectivity(self) -> Dict:
        """Check proxy connectivity by testing external access."""
        http_port = self.config.get('clash.http_port', 7890)
        test_url = 'http://www.gstatic.com/generate_204'
        proxy_url = f'http://127.0.0.1:{http_port}'

        try:
            response = requests.get(
                test_url,
                proxies={'http': proxy_url, 'https': proxy_url},
                timeout=10
            )

            if response.status_code in [200, 204]:
                return {
                    'category': 'connectivity',
                    'name': 'proxy_connectivity',
                    'status': 'pass',
                    'message': f'HTTP proxy connectivity OK ({response.status_code})',
                    'details': {
                        'http_code': response.status_code,
                        'test_url': test_url
                    }
                }
            else:
                return {
                    'category': 'connectivity',
                    'name': 'proxy_connectivity',
                    'status': 'fail',
                    'message': f'HTTP proxy returned unexpected code: {response.status_code}',
                    'details': {
                        'http_code': response.status_code,
                        'test_url': test_url
                    }
                }
        except Exception as e:
            return {
                'category': 'connectivity',
                'name': 'proxy_connectivity',
                'status': 'fail',
                'message': f'Proxy connectivity test failed: {e}',
                'details': {'test_url': test_url}
            }

    def format_terminal(self, results: Dict) -> str:
        """
        Format results for terminal output.

        Args:
            results: Health check results

        Returns:
            Formatted string
        """
        lines = []
        lines.append("╭─────────────────────────────────────────╮")
        lines.append("│  🏥 Lab Remote Bootstrap 健康检查       │")
        lines.append("╰─────────────────────────────────────────╯")
        lines.append("")

        # Group by category
        categories = {}
        for check in results['checks']:
            cat = check['category']
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(check)

        # Service status
        if 'service' in categories:
            lines.append("📦 服务状态")
            for check in categories['service']:
                status_icon = "✓" if check['status'] == 'pass' else "✗"
                color = "\033[32m" if check['status'] == 'pass' else "\033[31m"
                lines.append(f"  {color}{status_icon}\033[0m {check['message']}")
            lines.append("")

        # Port checks
        if 'port' in categories:
            lines.append("🌐 端口检查")
            for check in categories['port']:
                status_icon = "✓" if check['status'] == 'pass' else "✗"
                color = "\033[32m" if check['status'] == 'pass' else "\033[31m"
                lines.append(f"  {color}{status_icon}\033[0m {check['message']}")
            lines.append("")

        # Connectivity
        if 'connectivity' in categories:
            lines.append("🔗 连通性测试")
            for check in categories['connectivity']:
                status_icon = "✓" if check['status'] == 'pass' else "✗"
                color = "\033[32m" if check['status'] == 'pass' else "\033[31m"
                lines.append(f"  {color}{status_icon}\033[0m {check['message']}")
            lines.append("")

        # Summary
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        summary = results['summary']
        if summary['failed'] == 0:
            lines.append(f"\033[32m✅ 所有检查通过 ({summary['passed']}/{summary['total']})\033[0m")
        else:
            lines.append(f"\033[31m❌ 检查失败 ({summary['passed']}/{summary['total']} 通过)\033[0m")
        lines.append(f"运行时间: {summary['duration_seconds']}s")

        return '\n'.join(lines)

    def format_json(self, results: Dict) -> str:
        """
        Format results as JSON.

        Args:
            results: Health check results

        Returns:
            JSON string
        """
        return json.dumps(results, indent=2, ensure_ascii=False)
