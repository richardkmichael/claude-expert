# Claude Code Analysis - The SDK Parent Managed-Settings Tier

Verified against: cli.prettier.js 2.1.309 (2026-11-02)

How Claude Code treats managed settings that a host process passes in with `--managed-settings` (the
Agent SDK `managedSettings` option), and how that tier composes with the admin managed sources:
server-managed settings, MDM (macOS plist / HKLM) and `managed-settings.json`. Claude Desktop is the
main producer of this tier; the Desktop side is in `desktop/analysis/DEPLOYMENT_MODES.md`, "Managed
settings passed to Claude Code".

## The flag

`--managed-settings` takes inline JSON only. There is no file-path form, unlike `--settings`. The
value is trimmed and parsed during eager settings load. Anything other than a JSON object is dropped
with the warning `--managed-settings ignored: invalid JSON object`, and the tier is then marked
invalid. A host-supplied tier that is invalid counts as unreadable policy where the parent tier
participates, so the fail-closed checks that guard `allowedProviders` and similar treat it as
unreadable rather than absent.

The parsed object is validated against the settings schema under the source name
`parent managed settings`. `managedMcpServers`, `isolation` and `attributionProjectPolicy` are
ignored from it with
`"<key>" is only honored from the organization's managed settings sources (server-managed, MDM, managed-settings.json), not from settings a host passes in, and was ignored here.`
`managedMcpServers` is kept when `CLAUDE_CODE_ENTRYPOINT` is `claude-desktop-3p` or `local-agent`.

Relocate with `rg -n 'managed-settings ignored: invalid JSON object'` and
`rg -n '"parent managed settings"'`.

## Restrictive-only filter

The parent tier never enters policy as written. Claude Code first reduces it to a restrictive slice.
Only these values survive:

- Locks and switches: `allowManagedHooksOnly` (also set by `disableAllHooks`),
  `disableSkillShellExecution`, `disableCommandPluginSources`, `disableSideloadFlags`,
  `allowManagedMcpServersOnly`, `disableClaudeAiConnectors`, `syncClaudeAiSkills: false`,
  `syncClaudeAiPlugins: false`, `remoteTools.allowUnattendedServing: false`,
  `disablePluginDirectory`, `allowManagedPermissionRulesOnly`, `disableAutoMode: "disable"`,
  `remoteControl.shareHostProfile` of `off` or `basic`, attribution switched off,
  `enforceAvailableModels: true`, `availableModelsMatch: "exact"`.
- Lists that only narrow: `strictPluginOnlyCustomization`, `deniedMcpServers`,
  `blockedMarketplaces`, `deniedModels`, empty `allowedHttpHookUrls` / `httpHookAllowedEnvVars`.
- The allowlists `allowedMcpServers`, `availableModels`, `strictKnownMarketplaces` and
  `allowedProviders`, and `forceLoginOrgUUID`, each only when the admin tiers do not set it.
- `permissions.deny` and `permissions.ask` (a rule starting with `!` is dropped with
  `Ignoring <deny|ask> rule "…" from the parent process's managed settings`),
  `permissions.disableBypassPermissionsMode`, `permissions.disableAutoMode`,
  `permissions.blockReadsOutsideWorkingDirectories`, and `permissions.allow` /
  `permissions.additionalDirectories` unless an admin tier sets `allowManagedPermissionRulesOnly`.
- `sandbox.network.deniedDomains`, `sandbox.filesystem.denyRead` / `denyWrite`, the deny and mask
  forms of `sandbox.credentials`, `sandbox.network.allowedDomains` and
  `sandbox.filesystem.allowRead` unless an admin tier locks them with `allowManagedDomainsOnly` /
  `allowManagedReadPathsOnly`, and the restrictive sandbox locks.

Every other key is dropped, including `channelsEnabled`, `allowedChannelPlugins`, `processWrapper`,
`env`, `hooks`, `enabledPlugins`, `apiKeyHelper` and the other credential helpers, and
`permissions.defaultMode`. A host therefore cannot use `--managed-settings` to grant a capability
that a policy gate reads from `policySettings`: the channel gate, for example, never sees a
`channelsEnabled` or `allowedChannelPlugins` from this tier.

Relocate the filter with `rg -n "from the parent process's managed settings"`; it is the function
that builds the slice key by key, returning it after the `sandbox.credentials` block.

## Precedence against the admin sources

`parentSettingsBehavior` (`first-wins` | `merge`), read from the admin winner, decides whether the
parent slice joins policy:

| Admin managed sources present                    | Parent slice                                              |
| ------------------------------------------------ | --------------------------------------------------------- |
| none                                             | the sole policy tier, still restrictive-only              |
| any, `parentSettingsBehavior` unset / first-wins | dropped; the admin tiers are the only policy source       |
| any, `parentSettingsBehavior: "merge"`           | unioned under the admin winner, which wins every conflict |

The default flips to `merge` in a gateway session Claude Desktop's Code tab launched, which the
check reads from `CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST`, `CLAUDE_CODE_USE_GATEWAY` and the
entrypoint.

So with `/Library/Application Support/ClaudeCode/managed-settings.json` present and no
`parentSettingsBehavior: "merge"` in it, Desktop's `--managed-settings` contributes nothing. The
file wins whole, not key by key. With `merge`, the parent slice adds restrictions under it.
`managedSourcesBehavior` composes the admin sources with one another; `--managed-settings` and HKCU
never take part in that merge.

Relocate with `rg -n 'Controls whether the SDK parent tier'` (the schema description) and
`rg -n '"merge" : "first-wins"'` for the default resolution (the match inside a
`parentSettingsBehavior ??` expression).

Tripwire: □ `--managed-settings` inline JSON only, non-object ignored with a warning □ restrictive
slice drops `channelsEnabled` / `allowedChannelPlugins` / `processWrapper` □ admin tier present
without `merge` drops the parent □ `merge` default only for Desktop-launched gateway sessions.
