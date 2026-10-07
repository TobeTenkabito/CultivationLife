(() => {
  const num = n => Number(n || 0).toLocaleString('zh-CN', {maximumFractionDigits: 1});
  window.renderOrganizationFinance = (root, data) => {
    if (!data) return;
    const section = document.createElement('details');
    section.className = 'doctrine-entry organization-finance';
    const title = document.createElement('summary');
    title.textContent = `财政账目 · 府库 ${num(data.balance)} 灵石`;
    section.append(title);
    const metrics = document.createElement('div');
    metrics.className = 'family-metrics';
    for (const [label, value] of [['最近结算收入', data.income], ['已付开支', data.expense], ['供养缺口', data.shortfall], ['福利应付', data.benefit_due], ['福利实付', data.benefit_paid]]) {
      const row = document.createElement('span'), name = document.createElement('small'), amount = document.createElement('b');
      name.textContent = label; amount.textContent = num(value); row.append(name, amount); metrics.append(row);
    }
    section.append(metrics);
    const note = document.createElement('p');
    note.className = 'muted';
    note.textContent = `按实际年数结算，府库不足时减少支付。${data.product ? `驻地产出：${data.product}，最近售出 ${num(data.produced)} 件。` : ''}`;
    section.append(note); root.append(section);
  };
})();
