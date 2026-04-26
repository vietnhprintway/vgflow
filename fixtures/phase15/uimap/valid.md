# UI-MAP — fixture (valid 5-field-per-node + ownership tags)

```json
{
  "version": "1",
  "phase_id": "fixture",
  "root": {
    "tag": "PageLayout",
    "id": "page-root",
    "classes": ["min-h-screen", "bg-gray-50"],
    "children_count_order": {
      "count": 2,
      "order": ["topbar-1", "main-1"]
    },
    "props_bound": {},
    "text_content_static": null,
    "owner_wave_id": "wave-1",
    "children": [
      {
        "tag": "Topbar",
        "id": "topbar-1",
        "classes": ["h-14", "border-b"],
        "children_count_order": { "count": 1, "order": ["title"] },
        "props_bound": { "title": "props.title" },
        "text_content_static": null,
        "owner_wave_id": "wave-1",
        "owner_task_id": "T-1",
        "children": [
          {
            "tag": "h1",
            "classes": ["text-xl", "font-semibold"],
            "children_count_order": { "count": 0, "order": [] },
            "props_bound": {},
            "text_content_static": "Sites"
          }
        ]
      },
      {
        "tag": "MainContent",
        "id": "main-1",
        "classes": ["flex-1"],
        "children_count_order": { "count": 1, "order": ["table-1"] },
        "props_bound": { "rows": "state.sites" },
        "text_content_static": null,
        "owner_wave_id": "wave-2",
        "owner_task_id": "T-3",
        "children": [
          {
            "tag": "SitesTable",
            "id": "table-1",
            "classes": ["w-full"],
            "children_count_order": { "count": 0, "order": [] },
            "props_bound": { "data": "state.sites", "onEdit": "handleEdit" },
            "text_content_static": null
          }
        ]
      }
    ]
  }
}
```
