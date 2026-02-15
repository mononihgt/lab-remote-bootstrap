把 Clash 相关文件放在这个目录：

- 内核二进制（文件名不限，脚本会自动识别 `CrashCore` / `mihomo*` / `clash*`）
- `config.yaml`（通常是隐私内容，建议用户自己放）
- `geoip.dat`
- `geosite.dat`

如果自动识别失败，可在 `*.env` 中设置：

- `CLASH_CORE_FILE=你的内核文件名`
