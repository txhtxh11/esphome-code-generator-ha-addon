# ESPHome Code Generator — Home Assistant Add-on

> 在 Home Assistant 里用网页界面生成 ESPHome YAML：支持 ESP8266 / ESP32、ESPHome + HomeKit 双协议，内置中移铁通 CMPOWER W1 智能排插完整配置。

## 安装

1. Home Assistant → **设置** → **加载项** → **加载项商店**
2. 右上角 `⋮` → **仓库**，添加：

   ```
   https://github.com/txhtxh11/esphome-code-generator-ha-addon
   ```

3. 刷新，安装 **ESPHome Code Generator** → 启动 → 打开 Web UI

## 配置

`esphome_code_generator/config.json`：

| 项 | 说明 |
|---|---|
| `ingress_port` | 6052（从侧边栏直接打开） |
| `ports` | `6052/tcp` |
| `map` | `config:rw`、`share:rw` |
| `options.esphome_config` | 可选，指定 ESPHome 配置目录 |

## 目录

```
esphome_code_generator/
├── config.json      # add-on 元数据
├── Dockerfile
├── run.sh
├── code_generator.py
└── index.html       # 生成器页面
docker-compose.yml   # 单独跑（不走 HA）时用
```

## 单独运行（不用 HA）

```bash
docker compose up -d
# 然后访问 http://<host>:6052
```

## 相关仓库

- [ha-addon-repo](https://github.com/txhtxh11/ha-addon-repo) —— 集合版 add-on 仓库（含 ESPHome YAML 生成器）
- [cmpower](https://github.com/txhtxh11/cmpower) —— CMPOWER W1 智能排插 ESPHome 配置

## 许可证

本项目采用 MIT 许可证，详见 [LICENSE](LICENSE)。