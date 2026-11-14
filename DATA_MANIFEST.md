# Dish AI Data Manifest

Large training data lives outside this source repo. Two moves were made:

| Date | Moved | Size |
|---|---|---|
| 2026-09-12 | `cls_poc`, `cls_poc31`, `release_data`, `class_names.csv` | 22G |
| 2026-09-19 | `cls_full` (165,320 files), `cls_v200` (17,963), `cls_l200` (1,413) | 18G |

## External Location

- Current archive: `/Users/zackgu/ProjectData/dish-ai-data`
- Former path: `/Users/zackgu/Projects/Evergrande Weight Loss Group/dish-ai/data`
- Approximate size at move time: 22G (2026-09-12) + 18G (2026-09-19)

## Local Rule

`dish-ai/data/` inside the project is a placeholder/scratch path only. It is intentionally ignored by Git. Keep source code, model manifests, and deployment-ready lightweight assets in the repo; keep raw training datasets and split images under `/Users/zackgu/ProjectData`.

If a training or evaluation command expects `dish-ai/data`, either point it at `/Users/zackgu/ProjectData/dish-ai-data` or create a documented compatibility link deliberately.

## Compatibility Symlinks (2026-09-19)

Three symlinks were created deliberately, so absolute paths already recorded in build provenance keep resolving:

- `dish-ai/data/cls_full` -> `/Users/zackgu/ProjectData/dish-ai-data/cls_full`
- `dish-ai/data/cls_v200` -> `/Users/zackgu/ProjectData/dish-ai-data/cls_v200`
- `dish-ai/data/cls_l200` -> `/Users/zackgu/ProjectData/dish-ai-data/cls_l200`

They cover `dish-ai/runs/cls/full208/args.yaml` (`data: .../dish-ai/data/cls_full`) and the `trainingDataRoot` string in `ios-next/HDFZ/Resources/Recognition/foodvision-208-manifest.json`. Both are historical records; neither is rewritten. `RecognitionModelInfo` does not decode `trainingDataRoot`, so that field is provenance only and has no runtime effect.

The links sit under the gitignored `dish-ai/data/` path and are not tracked. Moving a dataset back into the repo would collide with the link — remove it first.
