"""练习判定相关的共享实现。

改版 M4 起，旧练习链路（``exercise_attempts`` + validator/repository/service）
已下线，本包只剩两件事：

* ``assertion_runtime``：v2 断言 DSL 的求值运行时（沙箱内也能跑）；
* ``assertions``：断言定义的校验、尾巴渲染与结果汇总。

``models`` 里的 ``ExerciseAttempt`` 仅为历史数据留存（表已冻结只读，不再写入），
不再是本包的对外入口。
"""
