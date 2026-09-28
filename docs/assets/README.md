# README visuals

- `workspace.png` and `results.png` are screenshots of the actual local Streamlit app with the bundled synthetic sample.
- `sample-preview.gif` is a two-frame slideshow of those complete screenshots, scaled proportionally into the same frame without additional cropping. It is not a live screen recording and does not show evidence expansion or report downloading.
- `repo-witness-banner.svg` and `claim-trace.svg` are editable vector illustrations. The trace uses the real sample import in `sample_repo/tests/test_app.py:1`.

To rebuild the slideshow from the repository root, install the optional asset tool and run:

```bash
python -m pip install Pillow==11.3.0
python scripts/build_readme_preview.py
```

Pillow is only needed to regenerate the GIF; it is not an app dependency. Font rendering can vary across operating systems. The README also links the still screenshots so the preview can be read without animation.
