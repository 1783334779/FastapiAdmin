/** 个人审批只依赖登录和后端任务归属，不借用项目列表/流程配置的菜单权限。 */
export function isPersonalWorkflowPath(path: string): boolean {
  return /^\/workflow\/tasks(?:\/[1-9]\d*)?\/?$/.test(path);
}
