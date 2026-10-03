# README visuals

- `repo-witness-banner.svg` matches the paper-and-ink application palette.
- `claim-trace.svg` illustrates the actual `sample_repo/tests/test_app.py:1` import and sample verdict counts.
- `change-review.svg` illustrates the actual worker-service comparison: two flagged claims, one unchanged dependency, and one claim with no evidence.
- `sample-preview.gif` alternates complete renders of those two walkthroughs on equal 1200 × 520 canvases, without cropping. These are illustrations of actual results, not app screenshots or a screen recording. The README links both still SVGs for readers who prefer a static view.
- `workspace.png` and `results.png` are retained historical screenshots of the previous dark application UI. They are no longer used in the main README.

To rebuild the illustrated preview from the repository root, install the optional asset tools and run:

```bash
python -m pip install Pillow==11.3.0 resvg-py==0.5.0
python scripts/build_readme_preview.py
```

These tools are only needed to regenerate the GIF; they are not app dependencies. Font rendering can vary across operating systems. SVGs use local Georgia, Arial, and Consolas fonts, with generic fallbacks, and contain no scripts or remote resources.
