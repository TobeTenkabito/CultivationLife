"""Export original Nobunaga/Seimei paintings through the existing skin pipeline."""
from scripts.prepare_swimwear_assets import ROOT, main

if __name__ == '__main__':
    main(ROOT / 'design/historical-skins-20261028', ROOT / 'web/assets/pixel/historical',
         'base.historical_manifest')
    from scripts.prepare_historical_effects import main as effects
    effects()
