# GitHub任务管理

规格：https://github.com/xk309/xiangsi_agent/issues/1 。任务 #2—#7 按原生依赖关系依次实施。

使用GitHub CLI或GitHub REST API读取、更新任务。多行正文通过文件或结构化JSON传递。凭据由已有Git登录提供，禁止显示、保存至源码或提交。每项完成后提供验证结果再关闭；父规格在全部验收完成前保持打开。

PR不作为外部需求收集入口。开发使用codex/分支，推送用户明确指定的仓库。
