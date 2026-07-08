# ESP Component Registry 发布说明

## 1. 发布对象

发布到 ESP Component Registry 的对象是：

```text
plugins/remote_udp_logger/components/remote_udp_logger
```

桌面工具 `host_tool` 不作为 IDF component 上传。建议放在 GitHub Release 里，例如：

```text
UdpLogViewer_package.zip
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

## 9. 实战记录与常见坑（2026-07 首次发布）

以下是 0.1.1 首次发布时实际踩过的坑，按发生顺序记录，供下次发布对照。

### 9.1 GitHub 仓库推送（从主仓库抽取插件目录）

插件在主仓库的 `plugins/remote_udp_logger/` 子目录里，公开仓库
`github.com/XianJieLianMeng/remote_udp_logger` 以该目录为根。用 subtree split
抽取只含该目录的独立提交历史：

```powershell
git subtree split --prefix=plugins/remote_udp_logger -b rul-export
git push https://github.com/XianJieLianMeng/remote_udp_logger.git rul-export:main
git branch -D rul-export
```

坑：GitHub 建仓时如果勾选了自动生成 README/.gitignore，首次推送会被拒
（non-fast-forward）。不要 force push，用无关历史合并保住双方提交：

```powershell
git fetch https://github.com/XianJieLianMeng/remote_udp_logger.git main
git worktree add <临时目录> rul-export
git -C <临时目录> merge <远程初始提交SHA> --allow-unrelated-histories -X ours -m "chore: 合并初始提交"
git push https://github.com/XianJieLianMeng/remote_udp_logger.git rul-export:main
```

注意 FETCH_HEAD 是主工作区专属引用，在 worktree 里要用提交 SHA 合并。
后续增量发布重复 split + push 即可（快进，无冲突）。

### 9.2 Namespace：组织名需要人工审批

- 用 GitHub 登录 components.espressif.com 后，个人用户名的 namespace 自动可用。
- 组织 namespace（如 `xianjielianmeng`）要在 Settings -> Namespaces 页面填表申请，
  状态会显示 Pending，需等 Espressif 人工批准后才能上传。

### 9.3 认证的三个坑

1. **`compote` 只在 ESP-IDF 环境里有**。普通 PowerShell 会报
   "compote is not recognized"。先执行
   `. D:\qrs_software\Esp32\Espressif\Initialize-Idf.ps1 -IdfId <id>`
   或直接用开始菜单的 "ESP-IDF PowerShell"。
2. **`--dry-run` 不校验令牌**。dry-run 通过不代表能正式上传——它只验证包结构，
   正式上传才需要 API token。
3. **旧令牌死循环**：现象是 `login` 报 "already logged in" 而上传报
   "Token not found"（令牌服务端早已吊销，本地却还存着，`logout` 也清不干净）。
   令牌配置文件在 `$IDF_TOOLS_PATH\idf_component_manager.yml`
   （本机为 `D:\qrs_software\Esp32\Espressif\`，不在用户目录）。
   修复：备份后直接删掉该文件，再重新认证。

### 9.4 最稳的认证方式：网页手动生成令牌

浏览器登录后到 <https://components.espressif.com/settings/tokens> 创建
Access Token（勾选 `write:components`），然后在同一个 ESP-IDF 终端里：

```powershell
$env:IDF_COMPONENT_API_TOKEN = "<网页生成的令牌>"
compote component upload --project-dir plugins\remote_udp_logger\components\remote_udp_logger --namespace xianjielianmeng --name remote_udp_logger
```

环境变量优先于配置文件，绕开 login/logout 的状态问题；令牌只对当前窗口生效。

### 9.5 其他

- `compote component pack` 的 `--dest-dir` 必须和项目同盘符（跨盘符会触发
  `ValueError: path is on mount 'C:'`，是 relpath 的已知问题）。
- 同一版本号只能上传一次；任何改动都要升 `version` 并补 `CHANGELOG.md` 条目。
