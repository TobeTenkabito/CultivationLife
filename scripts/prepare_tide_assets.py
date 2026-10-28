"""Pack the achievement swimwear paintings without reconstructing anatomy."""
from scripts.prepare_swimwear_assets import ROOT, main

if __name__ == '__main__':
    main(ROOT / 'design/tide-swim-20261028', ROOT / 'web/assets/pixel/tide', 'base.tide_manifest')
