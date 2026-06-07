# playwright-cli Command Reference

## Core Commands

```bash
playwright-cli open                          # Open browser
playwright-cli open <url>                    # Open browser and navigate
playwright-cli open <url> --persistent       # Reuse browser profile (auth cookies)
playwright-cli open <url> --headed           # Show browser window
playwright-cli open <url> --persistent --headed  # Both (recommended for testing)
playwright-cli goto <url>                    # Navigate to URL
playwright-cli close                         # Close browser
playwright-cli kill-all                      # Kill all browser sessions
```

## Sessions

Always use named sessions to avoid conflicts:

```bash
playwright-cli -s=bugbash open <url> --persistent --headed
playwright-cli -s=bugbash click e15
playwright-cli -s=bugbash snapshot
playwright-cli -s=bugbash close
```

## Interactions

```bash
playwright-cli click <ref>           # Click element (e.g. click e152)
playwright-cli dblclick <ref>        # Double-click
playwright-cli fill <ref> "text"     # Clear field and type
playwright-cli type "text"           # Type into focused element
playwright-cli select <ref> "value"  # Select dropdown option
playwright-cli check <ref>           # Check checkbox
playwright-cli uncheck <ref>         # Uncheck checkbox
playwright-cli hover <ref>           # Hover over element
```

## Keyboard

```bash
playwright-cli press Enter
playwright-cli press Tab
playwright-cli press Escape
playwright-cli press ArrowDown
playwright-cli press ArrowUp
```

## Navigation

```bash
playwright-cli go-back
playwright-cli go-forward
playwright-cli reload
```

## Snapshots

After every command, playwright-cli outputs a snapshot reference:

```
> playwright-cli goto https://example.com
### Page
- Page URL: https://example.com/
- Page Title: Example Domain
### Snapshot
[Snapshot](.playwright-cli/page-2026-02-14T19-22-42-679Z.yml)
```

Take a snapshot on demand:

```bash
playwright-cli snapshot
playwright-cli snapshot --filename=my-snapshot.yaml
```

**The snapshot YAML is an accessibility tree.** Every interactive element has a `[ref=eNN]` identifier. You MUST read the snapshot file and use these refs for interactions.

Example snapshot content:

```yaml
- navigation "Main":
    - link "Datasets" [ref=e12]
    - link "My contracts" [ref=e15]
    - link "My domains" [ref=e18]
- main:
    - heading "Kusto Datasets" [level=1]
    - button "Add filter" [ref=e42]
    - table:
        - row:
            - cell "TestDataset1" [ref=e55]
```

To click "My contracts": read the snapshot, find `[ref=e15]`, run `playwright-cli click e15`.

## Screenshots

```bash
playwright-cli screenshot                           # Save to default path
playwright-cli screenshot --filename=page.png       # Save to specific path
playwright-cli screenshot <ref>                     # Screenshot a specific element
```

## Tabs

```bash
playwright-cli tab-list
playwright-cli tab-new <url>
playwright-cli tab-select 0
playwright-cli tab-close
```

## Dialog Handling

```bash
playwright-cli dialog-accept
playwright-cli dialog-accept "confirmation text"
playwright-cli dialog-dismiss
```

## Evaluation

```bash
playwright-cli eval "document.title"
playwright-cli eval "el => el.textContent" e5
```
