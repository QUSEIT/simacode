# 实现human in loop特性
在.simacode/config.yaml中增加一个控制选项react=>confirm_by_human, 默认为false，如果设置为true,
在使用react对话模式的时候，如果AI规划出来了子任务（engine.py 266行开始），则告知用户详情并等待用户确认或者更改计划，之后再根据用户确认和更改后的计划来继续执行
