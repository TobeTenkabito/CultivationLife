"""Pack the 1890s gunslinger and Integration swimwear originals, retaining alpha."""
from scripts.prepare_swimwear_assets import ROOT, main

if __name__ == '__main__':
    main(ROOT / 'design/frontier-swim-20261027', ROOT / 'web/assets/pixel/frontier',
         'base.frontier_manifest')
