# ============================================================================
# 生成 SUMO 仿真路网 (Grid Network)
# ============================================================================
# 参数说明:
# --grid                        : 采用网格形状生成路网
# --grid.number=15              : 生成 15x15 的网格交叉口
# --grid.length=200             : 每个网格的道路长度为 200 米
# --output-file=...             : 指定生成的路网 XML 文件保存路径
# --tls.guess true              : 自动为交叉口生成和配置交通信号灯
# --tls.default-type actuated   : 默认信号灯类型为感应式 (actuated, 根据车流动态分配时间)
# --default.lanenumber 3        : 默认每条道路的车道数为 3 条
# --default.speed 11.11         : 默认限速为 11.11 m/s (约等于 40 km/h)
# ============================================================================
netgenerate --grid --grid.number=15 --grid.length=200 --output-file=configs/optimal_cbd.net.xml --tls.guess true --tls.default-type actuated --default.lanenumber 3 --default.speed 11.11