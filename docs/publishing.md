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

## 2. 发布前必须确认

`components/remote_udp_logger/idf_component.yml` 的 `maintainers/url/repository/
documentation/issues` 字段已填写（指向 `github.com/XianJieLianMeng/remote_udp_logger`）。
上传前确认该仓库真实存在且公开，否则先改成实际的托管地址。

同时确认：

```yaml
version: "0.1.0"
license: "MIT"
dependencies:
  idf: ">=5.0"
examples:
  - path: "examples/basic"
```

每次发布：

1. 升级 `version`（发布过的版本号不能重复上传），
2. 在 `CHANGELOG.md` 增加对应版本条目，
3. 运行 `python host_tool\sync_from_scripts.py --check` 确认桌面工具没有漂移。

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
  --namespace xianjielianmeng `
  --name remote_udp_logger `
  --dry-run
```

namespace 为用 GitHub 组织 `XianJieLianMeng` 登录注册表后的默认小写形式
`xianjielianmeng`；如实际分配的 namespace 不同，以注册表页面显示为准。

## 6. 正式发布

```powershell
compote component upload `
  --project-dir plugins\remote_udp_logger\components\remote_udp_logger `
  --namespace xianjielianmeng `
  --name remote_udp_logger
```

如果组件不存在，Registry 会自动创建组件。

## 7. 其他项目接入

发布后，其他 ESP-IDF 项目可以执行：

```powershell
idf.py add-dependency "xianjielianmeng/remote_udp_logger^0.1.1"
```

然后在代码里：

```cpp
#include "remote_udp_logger.h"

RemoteUdpLogger::SetDeviceId("90e5b1aeca9a");
RemoteUdpLogger::Initialize();
```

## 8. 发布检查清单

- `components/remote_udp_logger/idf_component.yml` 信息真实（url/repository 指向真实公开仓库）。
- `components/remote_udp_logger/LICENSE` 存在。
- `components/remote_udp_logger/README.md`（英文）与 `README_CN.md` 能独立说明用法。
- `components/remote_udp_logger/CHANGELOG.md` 包含本次版本条目。
- `components/remote_udp_logger/examples/basic` 能独立编译（`idf.py -C ... set-target esp32s3 build`）。
- `compote component pack` 成功（同时生成组件包与 examples 包）。
- `python host_tool\sync_from_scripts.py --check` 通过（桌面工具与 scripts/ 一致）。
- GitHub Release 已附带桌面工具包。
- Windows 桌面工具如果对外给客户使用，建议做代码签名。
