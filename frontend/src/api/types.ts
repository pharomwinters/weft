import type { components } from "./schema";

type Schemas = components["schemas"];

export type User = Schemas["UserOut"];
export type SessionInfo = Schemas["SessionOut"];
export type Workspace = Schemas["WorkspaceOut"];
export type Member = Schemas["MemberOut"];
export type Role = Member["role"];
export type Invitation = Schemas["InvitationOut"];
export type InvitationCreated = Schemas["InvitationCreatedOut"];
export type InvitationInfo = Schemas["InvitationInfoOut"];
export type AccountSession = Schemas["SessionItemOut"];
export type AdminUser = Schemas["AdminUserOut"];
export type ResetLink = Schemas["ResetLinkOut"];
export type AuditPage = Schemas["AuditPageOut"];
export type AuditEvent = Schemas["AuditEventOut"];
export type EnrolStart = Schemas["EnrolStartOut"];
export type EnrolConfirm = Schemas["EnrolConfirmOut"];
export type SecondFactor = Schemas["SecondFactorOut"];
export type RecoveryCodesResult = Schemas["RecoveryCodesOut"];
export type NextStep = Schemas["LoginOut"];
