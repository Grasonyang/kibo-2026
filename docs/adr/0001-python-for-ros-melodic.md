# ADR-0001：用 Python 寫，不用 Rust

- 狀態：已接受
- 日期：2026-11-03

## 背景

起初的選項是 Python 或 Rust。第 7 屆 Kibo-RPC 的程式不是 Android 應用，而是 ROS 1 Melodic 的 catkin package（`krpc_user`），在 JAXA 的 Docker image 裡建置與執行（Programming Manual 2.3、2.5.2）。環境固定為 GCC 7.5.0／C++14／**Python 3.6.9**／ROS 1 Melodic。官方範本只提供 Python（`scripts/user_template.py`）與 C++14（`src/user_template_node.cpp`）。提交物是 `packing.sh` 打包的原始碼，JAXA 對決賽程式還要做原始碼安全審查。

## 決定

任務邏輯用 **Python**，目標執行環境 3.6.9；本機工具鏈用 uv + Python 3.8。

## 理由

- Rust 不在官方工具鏈內：沒有 Rust 的範本、catkin 整合與審查流程。要用就得自己做 cross-compile 加 `rosrust` 或 FFI，而 Web 模擬器是 ARM64、映像由 JAXA 控制，風險全在我們。
- 這個競賽的瓶頸是路線規劃、ArUco 位姿估計與調參，不是執行效能；5 分鐘任務的迴圈用 Python 足夠。
- 範本、手冊範例都是 Python（rospy），改範本比重寫快。

## 考慮過的替代方案

- **C++14**：官方支援，效能最好，但開發與調參迭代比 Python 慢，且本專案沒有效能瓶頸。否決，若之後影像處理成為瓶頸可只把那一段改成 C++ 並重審本 ADR。
- **Rust（rosrust 或 FFI）**：見上，否決。

## 後果

- 程式碼不能用 Python 3.7 以後的特性。本機是 3.8，不會報錯的語法不代表 3.6 能跑；用 `vermin` 做靜態把關，最終以本機模擬器為準（見 [dev-env.md](../agents/dev-env.md)）。
- 第三方套件受限於 Melodic 映像內已有的版本。
- 不使用 `rust-clean-code` 等 Rust 規範；Python 的風格由 ruff 規定。
