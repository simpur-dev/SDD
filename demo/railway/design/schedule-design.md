---
id: DES-01
type: design
module: schedule
version: 1.0.0
status: active
title: 时刻计算设计
---

# 时刻计算设计

schedule 模块以"始发时刻 + 站间运行时分"推导各站时刻，实现 REQ-1。
调整发车时间时平移始发时刻即可重算后续各站。
