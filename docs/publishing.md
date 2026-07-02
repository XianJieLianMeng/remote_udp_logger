# ESP Component Registry 发布说明

## 1. 发布对象

发布到 ESP Component Registry 的对象是：

```text
plugins/remote_udp_logger/components/remote_udp_logger
```

桌面工具 `host_tool` 不作为 IDF component 上传。建议放在 GitHub Release 里，例如：

```text
XbellUdpLogViewer_package.zip
```

## 2. 发布前必须修改

编辑：

```text
components/remote_udp_logger/idf_component.yml
```

把下面这些字段从注释改成真实值：

```yaml
maintainers:
  - Your Name <you@example.com>
url: "https://github.com/your-org/remote_udp_logger"
repository: "https://github.com/your-org/remote_udp_logger.git"
documentation: "https://github.com/your-org/remote_udp_logger#readme"
issues: "https://github.com/your-org/remote_udp_logger/issues"
```

同时确认：

```yaml
version: "0.1.0"
license: "MIT"
dependencies:
  idf: ">=5.0"
```

版本号发布后不要重复上传同一个版本。如果改代码，需要升级版本，例如 `0.1.1` 或 `0.2.0`。

## 3. 本地打包校验

在仓库根目录运行：

```powershell
compote component pack `
  --project-dir plugins\remote_udp_logger\components\remote_udp_logger `
  --name remote_udp_logger `
  --dest-dir dist\remote_udp_logger_registry_pack
```

当前本机已验证 `pack` 可以成功生成：

```text
remote_udp_logger_0.1.0.tgz
```

## 4. 登录 Registry

```powershell
compote registry login
```

如果本机没有 `compote`，先确认 ESP-IDF Component Manager 已安装：

```powershell
python -m pip install idf-component-manager
```

## 5. Dry Run 校验

正式发布前先做 dry run：

```powershell
compote component upload `
  --project-dir plugins\remote_udp_logger\components\remote_udp_logger `
  --namespace your_namespace `
  --name remote_udp_logger `
  --dry-run
```

`your_namespace` 要换成你们在 ESP Component Registry 上的 namespace。

## 6. 正式发布

```powershell
compote component upload `
  --project-dir plugins\remote_udp_logger\components\remote_udp_logger `
  --namespace your_namespace `
  --name remote_udp_logger
```

如果组件不存在，Registry 会自动创建组件。

## 7. 其他项目接入

发布后，其他 ESP-IDF 项目可以执行：

```powershell
idf.py add-dependency "your_namespace/remote_udp_logger^0.1.0"
```

然后在代码里：

```cpp
#include "remote_udp_logger.h"

RemoteUdpLogger::SetDeviceId("90e5b1aeca9a");
RemoteUdpLogger::Initialize();
```

## 8. 发布检查清单

- `components/remote_udp_logger/idf_component.yml` 信息真实。
- `components/remote_udp_logger/LICENSE` 存在。
- `components/remote_udp_logger/README.md` 能独立说明用法。
- `components/remote_udp_logger/examples/basic` 能编译。
- `compote component pack` 成功。
- GitHub Release 已附带桌面工具包。
- Windows 桌面工具如果对外给客户使用，建议做代码签名。
