# Foreman UI design review: composition, organization, and interaction

> Saved in the repository at the user’s request. The observations and read-only
> review notes below describe the original review sessions on 2026-09-08,
> not subsequent implementation or this archival step. Screenshots are
> preserved alongside the reviews; live state changed between captures.

2026-09-08. Follow-up to [2026-09-08-methodology-functionality-review.md](2026-09-08-methodology-functionality-review.md); that review and its functional findings remain valid and are not replaced here.

Scope: live dashboard, project planning with Manager open/collapsed, queued sprint expansion, sprint board with activity open/collapsed, board overflow, filtered activity, task drawer and gate/history section, Roles, Settings, New Sprint, New Task, and rendered v6 mockup. Browser API interception blocked all non-GET requests. No forms were saved or submitted. The live engine continued independently; FOR-9 was at a human gate and FOR-12 was running during this capture. This report does not assess their unfinished implementation changes.

## Design diagnosis

Foreman's interface has a recognizable palette but no consistently applied composition or interaction grammar. Scope, importance, and placement do not correspond reliably. Engine health, sprint lifecycle, task status, configuration, diagnostics, editing, and navigation compete in shared containers. The same visual treatments mean different things; similar actions behave differently across views.

That produces the feeling of an assembled interface: features have acquired somewhere to live, but the page has not been recomposed around the resulting user workflow. This diagnosis is an inference from the rendered product and component structure, not a claim about the intentions of its authors.

Keeping the dark palette is entirely compatible with correcting these problems. A color refresh alone would leave most of them intact.

## 1. Sprint identity has been squeezed into a toolbar

The entire sprint header occupies 50px at 1440px desktop width. Its title group—including pencil and status—gets about 297px. The title truncates while the right control group refuses to shrink. The goal is another single-line fragment alongside it. The full title is also repeated in the breadcrumb.

The title is the main identification of the object being viewed; it should own space rather than lose a contest with buttons. The two pencil icons imply field-level editing before the page has even established readable content. ACTIVE is repeated in the footer, RUNNING appears in the global shell, and engine residency appears between controls. These are different facts without a clearly expressed relationship.

The result is a continuous string of labels, icons, badges, and buttons with no convincing start, emphasis, or grouping. More gap between each item would not solve it.

Proposed composition:

- Navigation: Projects / Foreman / Sprint 54, with short identifiers appropriate to navigation.
- Identity: full sprint title as the page heading, with lifecycle status subordinate to it.
- Goal: a readable paragraph below the title.
- Sprint actions: one Edit sprint action, plus a contextual menu for lifecycle actions.
- Work controls: task view controls, New task, and Activity grouped together.
- Engine control: one project-scoped execution summary and Pause/Resume control, clearly distinct from sprint lifecycle.

Allow the full title to wrap. The 50px header height should not be an invariant. A hover tooltip is a fallback for compact navigation, not a replacement for the page heading.

Evidence: [foreman-design-sprint.png](assets/2026-09-08-ui-review/foreman-design-sprint.png); `frontend/src/styles.css:1565`, `:1620`; `frontend/src/App.jsx:805`.

## 2. Cancelled tasks occupy an undiscoverable second board row

Cancelled is appended as a fifth status section into a four-column grid. Its top was measured at y=1099 in a 1000px viewport. Its vertical position depends on the tallest column in the first row, which in this sprint is Done. A person has to scroll past empty space under other columns before learning another status section exists.

The board is teaching the reader that statuses are horizontal columns, then silently switches to a second row. The fixed footer makes the viewport look like a complete bounded workspace. The subdued scrollbar offers little indication of what is missing.

Use stable board semantics: do not wrap status columns onto another row. Keep Cancelled discoverable as a visible filter with a count, or in an explicitly labelled secondary history section. A list view can expose all status groups efficiently. If a board has more columns than fit, use deliberate horizontal scrolling with visible affordances or a different compact layout.

Done should not be allowed to dictate the discovery of unrelated content. Collapse or bound completed history deliberately, with a count and a clear way to inspect it.

Evidence: [foreman-design-sprint-bottom.png](assets/2026-09-08-ui-review/foreman-design-sprint-bottom.png); `frontend/src/App.jsx:989`; `frontend/src/styles.css:1698`.

## 3. The top bar has no coherent scope

Tokens, RUNNING, Roles, and a gear look like peer items. They are not: usage is an aggregate, running is runtime state, Roles opens shared cross-project configuration, and the gear opens project settings. The scope shift is communicated only after opening Roles.

On the all-projects screen, the shell displayed IDLE / No tokens used yet while the Foreman card displayed RUNNING and accumulated tokens. Even without diagnosing the underlying defaults, that is a confusing presentation: an apparently global status contradicts a visible project.

Keep the application shell primarily for navigation and application-level utilities. Put project runtime state inside project context. Put resource totals in a labelled usage summary, where their period and scope are explicit. Nest project configuration under a named project entry point. A shared configuration library needs an explicit workspace scope.

Evidence: [foreman-design-dashboard.png](assets/2026-09-08-ui-review/foreman-design-dashboard.png), [foreman-design-project-collapsed.png](assets/2026-09-08-ui-review/foreman-design-project-collapsed.png); `frontend/src/components.jsx:63`.

## 4. Roles exposes the implementation vocabulary before explaining the work

The dialog is a flat catalogue of Architect, Code Reviewer, Developer, Worker Fleet, Frontier Reviewer, Security Reviewer, and Triage Reviewer. Each gets model, backend, permission mode, and Save. Persistent/ephemeral appears in the heading. Some names repeat as human name plus nearly identical machine ID.

Missing from the first view: which roles this project actually uses, execution order, why a role exists, what it receives and produces, how model defaults resolve, and what projects a change affects. The current workflow is not visible here. The role descriptions available in TOML are not presented. An empty model field with “project default” does not explain the effective configuration for a particular project.

The primary configuration surface should explain a project's execution sequence: Develop → Test → Review → Merge approval → Merge. Each stage can expose its model, responsibility, and effective settings. Built-in steps should be visually distinct from agent steps. Human decisions should be explicit. These are views over the existing declarative workflow, not a proposal to hard-code it.

Keep reusable roles as an advanced, clearly shared library. Show where they are used and make edits' scope explicit. Multiple roles may be useful internally without making users manage seven apparently equal agents to understand one project.

Evidence: [foreman-design-roles.png](assets/2026-09-08-ui-review/foreman-design-roles.png); `frontend/src/components.jsx:2072`.

## 5. Settings is an unstructured configuration form squeezed into a drawer

A long scrolling drawer mixes autonomy, task selection, proof gating, models, token economy, judge endpoint configuration, workflow selection, resource limits, retention, and the test command. The default workflow appears after specialist judge configuration. That order follows accumulated settings more closely than the questions a user needs to answer.

“Autonomous” is both a top-level mode and a separate selection toggle. “Time limit per task (ms, 0 = off)” asks the operator to translate storage units and sentinel values. Model inheritance is described in harness/role terminology without showing the effective result. Some helper text is boxed and padded like another input, turning ordinary explanations into visual furniture.

Use a settings page with a small section navigation: Execution and approvals; Models; Limits; Repository and environment; Advanced/shared configuration. Present human units, explicit disabled states, readable labels, and effective values. Keep technical endpoint/cap details behind an advanced section. Stable Save/Discard feedback should belong to the section being edited.

Evidence: [foreman-design-settings.png](assets/2026-09-08-ui-review/foreman-design-settings.png); `frontend/src/components.jsx:1442`; `.form-hint` in `frontend/src/styles.css:3877` and `:3952`.

## 6. Project planning has useful groups but inconsistent interaction semantics

Active / Queue / Archive is a reasonable organization. Its execution is less successful:

- The active card is a large button containing many task-looking rows. Clicking a row opens the sprint, not the task.
- A queued sprint card opens an inline editor instead of navigating. Navigation then requires Open →.
- Expanded queued cards contain title/goal fields, task deletion, and a full task-creation form. Browsing a queue becomes editing a large nested document.
- Title and goal save on blur in the queued editor; they use explicit Save/Cancel in the sprint view.
- Cancel and Delete are continuously visible on a compact queued row, while its useful navigation action is hidden inside expansion.
- Completed tasks are crossed out and dimmed like discarded content, despite being useful project history.

Use a stable row contract: title opens the sprint; an explicit edit action edits it; a separate disclosure previews tasks; drag handles reorder. Task rows should either open tasks or read clearly as a noninteractive summary. Keep routine browsing and editing separate. Put destructive operations in an action menu.

Evidence: [foreman-design-project-collapsed.png](assets/2026-09-08-ui-review/foreman-design-project-collapsed.png), [foreman-design-queue-expanded.png](assets/2026-09-08-ui-review/foreman-design-queue-expanded.png); `frontend/src/components.jsx:414`.

## 7. Manager changes the page's composition before the user requests it

The 540px Manager pane opens by default, making a blank conversation a dominant part of project planning. The main content recenters when it collapses. Its collapsed affordance is a 32px vertical rail labelled AGENT, although the open pane was labelled Manager.

The main scroll container is also the centered, max-width content element. In the 1440×800 expanded-queue capture, its boundary is x=1244, while the Agent rail is at the far right. This places a scroll boundary inside a large unbounded gutter, disconnected from both the content edge and the companion panel. The issue is the ownership of scrolling, not merely scrollbar color.

Open Manager on request through a consistent horizontal label. Remember the user's pane preference. Keep the scroll viewport full width within its region; constrain the reading measure in an inner wrapper. Companion panels may scroll independently, but their boundaries should visually explain ownership. Opening them should follow a predictable resize or overlay policy.

Evidence: [foreman-design-project-open.png](assets/2026-09-08-ui-review/foreman-design-project-open.png), [foreman-design-project-collapsed.png](assets/2026-09-08-ui-review/foreman-design-project-collapsed.png), [foreman-design-queue-expanded.png](assets/2026-09-08-ui-review/foreman-design-queue-expanded.png); `frontend/src/styles.css:706`.

## 8. Activity has no clear relationship to project, sprint, task, or conversation

At project level, the prominent side surface is Manager. At sprint level, it becomes Activity. Collapsed versions are vertical AGENT and ACTIVITY rails. Selecting a task opens a drawer over activity. The composer targets a task while the feed remains sprint-scoped. A user must infer that reading a feed, speaking to the Manager, and guiding a developer are different interactions.

The feed gives every event a timestamp, event type, long task title, and body. Often the body repeats only the event type. Timestamp layout even separates AM/PM onto another line. Long scripts expand vertically. The “Agent” filter still included raw output and tool-result records in this inspection; it is not a simple readable narrative filter.

Define activity scope explicitly: Sprint activity / Task activity / Run details. Put a task's activity inside its own task view. Give sprint-wide activity a labelled tab or toolbar entry. Provide an operational summary stream with grouped operations and expandable command/output details. A technical log can remain available without determining the main feed's typography and information density.

Name the recipient next to any composer. Keep Manager as an intentional project-level assistant with consistent naming and entry point.

Evidence: [foreman-design-activity-filtered.png](assets/2026-09-08-ui-review/foreman-design-activity-filtered.png); `frontend/src/components.jsx:985`, `:2480`; earlier guidance delivery and occlusion findings still apply.

## 9. Task detail repeats the header crowding and breaks down further in history

The drawer header places key, long title, pencil, task type, status, and close button in a single flex row. The key nearly touches the title; metadata competes with the heading. The body begins with a large plain-text description before reaching criteria and decisions.

At the bottom, full-width red Cancel task and Delete task buttons have more visual mass than the small Approve and Deny controls. They sit between the decision form and history. This reverses the expected action hierarchy and interrupts the review sequence.

Run history has a 52px role column. Long machine labels such as `_BUILTIN:ORCHESTRATOR` visibly overlap the next column. The rows have a pointer cursor and hover styling without a corresponding navigation handler in this component. That advertises exploration that the row does not provide.

Use separate header lines for identity and metadata. Establish Overview / Changes / Checks / Activity sections or tabs. Put a pending decision and its consequence near the top, with supporting evidence easy to reach. Move deletion into an actions menu. Render run stages as readable names with duration and outcome; expose machine IDs in details. Every hover/click affordance should have a real purpose.

Evidence: [foreman-design-task-bottom.png](assets/2026-09-08-ui-review/foreman-design-task-bottom.png), prior [foreman-review-detail.png](assets/2026-09-08-ui-review/foreman-review-detail.png); `frontend/src/styles.css:2322`, `:2949`; `frontend/src/components.jsx:1102`.

## 10. Forms have inconsistent visual rhythm and ask too much too early

New Sprint devotes most of its initial height to a task editor nested inside “Initial tasks (optional).” It has two titles, nested labels, Add task, and Create sprint in the same composition. The user has to understand an intermediate task list before completing the main operation. Optional work should start as Add initial tasks and disclose the editor intentionally. If a draft is present, submitting the sprint must resolve that draft explicitly.

New Task exposes type, complexity, and dependencies alongside its essential content. Colored type choices look like output badges instead of a clear single-choice control. Feature is selected although the label calls it optional. Similar chips elsewhere use a different visual treatment.

The same `.form-group` receives spacing from different parent arrangements: modal bodies use a gap while nested task forms place repeated groups more tightly. The result is generous separation in one form and cramped labels in another. Tiny uppercase labels carry the same visual treatment as section headings elsewhere. Helper text sometimes becomes a bordered panel. The border hierarchy is doing too many unrelated jobs.

Use the same field anatomy everywhere: label, control, optional helper/error, consistent spacing to the next field. Distinguish section spacing from field spacing. Make optional metadata a compact disclosure. Give required prose enough initial writing space and a reliable expansion option.

Evidence: [foreman-design-new-sprint.png](assets/2026-09-08-ui-review/foreman-design-new-sprint.png), [foreman-design-new-task.png](assets/2026-09-08-ui-review/foreman-design-new-task.png), [foreman-design-settings.png](assets/2026-09-08-ui-review/foreman-design-settings.png); `frontend/src/components.jsx:1726`, `:1955`.

## 11. Typography and color do not express a dependable hierarchy

The problem is not simply small fonts. IDs, data labels, prose, navigation, buttons, and activity all occupy neighboring sizes and muted tones. There are too few differences that communicate importance, and too many incidental differences between specific components. Serif italic goals become ornamental secondary text even when the goal is essential. Long monospace prose is hard to scan. Uppercase, tracking, outlines, and pills are used repeatedly instead of a clear heading structure.

Gold means accent, selection, active workflow step, primary action, and human attention. Task-type chips add more categorical colors without much decision value. Completed tasks are dimmed; selected tasks and blocked tasks can both gain prominent borders. Meaning becomes harder to recognize quickly.

A starting specification to validate, not a universal prescription: page title 24–28px; section title 16–18px; body and controls 14px; metadata 12px; body line-height around 1.5. Use 8px for tight related items, 16px within groups, 24–32px between sections. Keep a small number of button sizes and semantic variants. Preserve the charcoal palette and warm accent while giving primary content normal reading contrast.

Reserve monospace primarily for identifiers, commands, and numeric columns. Keep prose upright and readable. Use restrained, consistent status color; low-value categories can be neutral. “Completed” should remain readable history.

## Content and interaction rules the product needs

| Element | Display rule | Interaction rule |
|---|---|---|
| Page-level sprint/task title | Full text, wrapping; never ellipsis-only | Named Edit action, stable edit layout |
| Breadcrumb | Compact identifier; truncation allowed as secondary navigation | Consistent navigation/switching |
| Sprint/task card title | Enough lines to distinguish real tasks | Opens that object; full title at destination |
| Sprint goal | Readable paragraph; bounded summary only with explicit expansion | Edited with sprint details |
| Description/criteria | Structured prose, real paragraphs/lists, readable measure | Expand long content; do not bury current decisions |
| Branch/path/IDs | Secondary; middle truncation where useful | Reveal/copy complete value |
| Status | One badge in the relevant scope | Link to explanation where needed |
| Usage | Labelled scope and period | Opens usage detail; not an unexplained global counter |
| Commands/tool output | Collapsed summary with clear expansion | Dedicated technical details |
| Editing | Consistent Save/Cancel, visible pending/error state | No hidden change in save semantics across views |
| Destructive actions | Secondary menu or clearly separated area | Named consequence, appropriate confirmation |
| Companion panels | Intentional entry, remembered preference, stable boundary | Same name open/closed; no unrelated content hidden beneath |

## Proposed information architecture

Application level: Projects and workspace settings, including shared role definitions.

Project level: Overview, Sprints, Activity, Settings. Manager is an explicit project utility, not a replacement for these surfaces.

Sprint level: readable identity and goal; task List/Board views; a visible Cancelled count/filter; sprint activity; Edit sprint and lifecycle actions.

Task level: readable identity, state, and next decision; Overview, Changes, Checks, Activity; task guidance with explicit recipient and delivery state.

Project execution settings: show the configured workflow as stages, effective model settings, review behavior, approvals, and limits. The shared role library is an advanced destination linked from the relevant stage.

These names and exact navigation forms should be tested as a coherent proposal. The important constraints are scope, stable entry points, and consistent editing—not the addition of more navigation chrome.

## Relationship to the mockup and implementation method

The v6 mockup looks more composed partly because its content is curated: “Sprint 3,” a short goal, a balanced set of cards, four statuses, and concise meaningful activity messages. Real data has long task and sprint names, asymmetric counts, more states, backend metadata, and full commands. The implementation retained tight layout assumptions while accumulating controls and content.

The mockup is therefore a useful direction but an insufficient content stress test. Preserving it literally would preserve some of its original weaknesses, including tiny text and fixed pane assumptions. Any revised UI reference should be explicitly approved as a direction change; this review does not alter the authoritative artifacts.

Before the next visual implementation, define page anatomy, content-length rules, common component variants, scroll ownership, and action scope. Review a representative set of real states together: long title, empty queue, many completed tasks, cancelled tasks, pending approval, expanded editor, activity open, Manager closed, narrow viewport. Require browser screenshots and journey checks for that set. A one-component-at-a-time CSS cleanup is unlikely to repair the cross-screen design.

## Suggested next task and retained findings

Suggested next task: a bounded design slice for sprint/task supervision that establishes the header, task list/board, activity entry, task detail, and editing conventions together in a reviewable prototype. Use it to agree the design grammar before applying it to the remaining screens. Preserve the backend architecture and treat the existing guidance-delivery and evidence-truth issues as explicit acceptance constraints.

Earlier guidance, completion evidence, async-state, responsive, and repository-memory findings remain in [2026-09-08-methodology-functionality-review.md](2026-09-08-methodology-functionality-review.md).

Deliverables: this review and 14 new browser screenshots in `/tmp/foreman-design-*.png`.

Validation: real browser navigation, panel collapse/expansion, dialog inspection, activity filtering, scroll-boundary and element geometry measurement, rendered mockup comparison, and source inspection. No mutation tests, rebuilds, or full suites in this follow-up. The earlier repo-memory validation passed; it is not a visual quality check.

Files changed in repository: none. Repository documentation updated: none. Branch: no new branch; checkout remains detached. Open limits: live data changed independently during capture; this is an expert design review, not observed usability testing with representative users. Proposed component sizes and architecture are design recommendations, not implemented or validated solutions.


## Preserved screenshots

- [foreman-design-activity-filtered.png](assets/2026-09-08-ui-review/foreman-design-activity-filtered.png)
- [foreman-design-dashboard.png](assets/2026-09-08-ui-review/foreman-design-dashboard.png)
- [foreman-design-mockup-sprint.png](assets/2026-09-08-ui-review/foreman-design-mockup-sprint.png)
- [foreman-design-new-sprint.png](assets/2026-09-08-ui-review/foreman-design-new-sprint.png)
- [foreman-design-new-task.png](assets/2026-09-08-ui-review/foreman-design-new-task.png)
- [foreman-design-project-collapsed.png](assets/2026-09-08-ui-review/foreman-design-project-collapsed.png)
- [foreman-design-project-open.png](assets/2026-09-08-ui-review/foreman-design-project-open.png)
- [foreman-design-queue-expanded.png](assets/2026-09-08-ui-review/foreman-design-queue-expanded.png)
- [foreman-design-roles.png](assets/2026-09-08-ui-review/foreman-design-roles.png)
- [foreman-design-settings.png](assets/2026-09-08-ui-review/foreman-design-settings.png)
- [foreman-design-sprint-bottom.png](assets/2026-09-08-ui-review/foreman-design-sprint-bottom.png)
- [foreman-design-sprint-no-activity.png](assets/2026-09-08-ui-review/foreman-design-sprint-no-activity.png)
- [foreman-design-sprint.png](assets/2026-09-08-ui-review/foreman-design-sprint.png)
- [foreman-design-task-bottom.png](assets/2026-09-08-ui-review/foreman-design-task-bottom.png)
