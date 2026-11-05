"""DOM contract and allocation comparison for shared UI factories in Chromium."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.set_content('<main id="fixture"></main>')
        page.add_script_tag(path=str(ROOT / 'web/ui-panels.js'))
        report = page.evaluate('''() => {
            // Original contracts differ for null, false, zero and the third argument.
            const legacy = {
                element: (tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;},
                textElement: (tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;},
                identifiedElement: (tag,text,id)=>{const n=document.createElement(tag);if(text)n.textContent=text;if(id)n.id=id;return n;}
            };
            let cases = 0;
            const rows = [];
            const measure = fn => {
                const start = performance.now();
                for(let i=0;i<50000;i++) fn('span', '机缘 '+(i%10), 'resource');
                return performance.now()-start;
            };
            for(const [key,old] of Object.entries(legacy)) {
                const current = GameUi[key];
                for(const tag of ['span','button','option','input'])
                    for(const text of [undefined,null,'',0,false,'<img src=x onerror=alert(1)>','机缘与𠮷'])
                        for(const extra of [undefined,null,'','resource']) {
                            const a=old(tag,text,extra),b=current(tag,text,extra);
                            if(a.outerHTML!==b.outerHTML || a.childNodes.length!==b.childNodes.length || b.isConnected)
                                throw Error('DOM contract changed: '+key);
                            cases++;
                        }
                const before=[],after=[];
                measure(old);measure(current);
                for(let i=0;i<15;i++) {
                    if(i%2) {after.push(measure(current));before.push(measure(old));}
                    else {before.push(measure(old));after.push(measure(current));}
                }
                const median=a=>a.sort((x,y)=>x-y)[Math.floor(a.length/2)];
                rows.push({helper:key,old_ms:median(before),shared_ms:median(after),iterations:50000});
            }
            const button=GameUi.element('button','办理','action');button.id='shared-action';
            button.disabled=true;window.__clicks=0;button.onclick=()=>window.__clicks++;
            document.querySelector('#fixture').append(button);
            return {cases,allocations:rows};
        }''')
        assert page.locator('#shared-action').is_disabled()
        page.evaluate("document.querySelector('#shared-action').click()")
        assert page.evaluate('window.__clicks') == 0
        page.evaluate("document.querySelector('#shared-action').disabled=false")
        page.locator('#shared-action').click()
        assert page.evaluate('window.__clicks') == 1
        browser.close()
    output = ROOT / 'build/ui-components.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"Shared UI passed: {report['cases']} DOM cases, real click and disabled control; timing: {output}")


if __name__ == '__main__':
    main()
