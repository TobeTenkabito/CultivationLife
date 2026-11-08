/* Ownership labels only. Never change visibility, eligibility or click handlers. */
(() => {
  const scopes = '.yaochi-practice,.earth-temple,.yaochi-gathering,.court-bureaus';
  const aliases={'asura-manifestation':'asura','buddhist-dharma':'buddhist','ghost-reincarnation':'ghost',
    'guixu-tide':'guixu','intrigue-coalitions':'intrigue','monster-bloodlines':'bloodline',monster:'bloodline',
    'monster-civilizations':'civilizations','sage-way':'sage','tianji-artifacts':'tianji','authored-techniques':'authored'};
  function mark(button, owner) { if (owner) {const key=owner.replace(/^official\./,'');button.dataset.dlc=aliases[key]||key;} }
  function scan(root) {
    if (!(root instanceof Element)) return;
    const buttons = [...(root.matches('button') ? [root] : []), ...root.querySelectorAll('button')];
    for (const button of buttons) {
      const local = button.closest('[data-dlc-scope]');
      if (local) mark(button, local.dataset.dlcScope);
      else if (button.closest(scopes)) mark(button, 'yaochi-westward');
      else if (button.dataset.dlc) mark(button,button.dataset.dlc);
    }
  }
  function page(button, nodes) {
    if (nodes.length && nodes.every(n => n.matches(scopes) || n.closest('[data-dlc-scope]'))) {
      mark(button, nodes[0].closest('[data-dlc-scope]')?.dataset.dlcScope || 'yaochi-westward');
    }
  }
  function start() {
    // Existing navigation is the ownership directory for dedicated DLC panels.
    document.querySelectorAll('[data-panel-target][data-dlc]').forEach(button => {
      const id = button.dataset.panelTarget;
      const content = document.getElementById(id + '-content') || document.getElementById(id + '-panel');
      if (content) content.dataset.dlcScope = button.dataset.dlc;
    });
    scan(document.body);
    new MutationObserver(records => {
      for (const record of records) for (const node of record.addedNodes) scan(node);
    }).observe(document.body, {childList:true, subtree:true});
  }
  window.DlcControls = {mark, page};
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, {once:true}); else start();
})();
