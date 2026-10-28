"""Export holiday originals using the established transparent costume pipeline."""
from scripts.prepare_swimwear_assets import ROOT, main

if __name__ == '__main__':
    main(ROOT / 'design/holiday-skins-20261027', ROOT / 'web/assets/pixel/holiday',
         'base.holiday_manifest')
    from scripts.prepare_christmas_effects import main as effects
    effects()
