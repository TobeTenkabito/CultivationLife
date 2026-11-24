window.RaceCouncil = (() => {
  const element = (tag, text) => {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    return node;
  };

  function directory(parent, system, member) {
    if (!system?.available) return;
    const book = element('details');
    book.className = 'race-factions';
    book.append(element('summary', member ? '本界宗门名录' : '地方山门名录'));
    for (const race of Object.values(system.races)) {
      const names = race.supported_factions.filter(f => (!f.kind || f.kind === 'sect') && (member || !f.active));
      if (!names.length) continue;
      const line = element('p');
      line.append(element('b', race.name), element('span', names.map(f => f.name).join('、')));
      book.append(line);
    }
    if (book.children.length > 1) parent.append(book);
  }

  function meeting(parent, system, race, game, submit) {
    const record = race.council;
    if (!record) return;
    const section = element('section');
    section.className = 'race-council';
    section.append(element('h3', '诸宗会商'));
    const members = race.supported_factions.filter(f => !f.kind || f.kind === 'sect');
    if (system.can_convene && race.id === system.player_race && members.length >= 2) {
      const form = element('form');
      form.className = 'governance-form';
      const topic = element('select'), target = element('select'), hint = element('small');
      topic.setAttribute('aria-label', '议案');
      target.setAttribute('aria-label', '议案所涉宗门');
      const topics = {
        rotate: ['各宗轮荐', '六个荐徒名额由各宗轮分，历届分得少的山门先取。'],
        sponsor: ['推举主办山门', '主办山门先取三席，其余三席由别宗轮分。'],
        amend: ['主办让席再议', '沿用上次议案，主办山门只留两席，其余四席重分。'],
        mediate: ['调让荐额', '从余席最多的山门调出一席，转给所选宗门。两家余席须相差两席以上。'],
        aid: ['同地周济', '两宗须同驻此地。出资山门留足三年供养，亲署拨款书后交割灵石。'],
        invite: ['延请客宗', '诸宗议定后遣使送上盟书。客宗若久受冷落，更愿改换门庭。'],
      };
      for (const [key, [name]] of Object.entries(topics)) {
        if (key !== 'amend' || record.counter) topic.add(new Option(name, key));
      }
      const button = element('button', '召集会商');
      button.type = 'submit';
      const stance = element('select');
      stance.setAttribute('aria-label', '本宗回函');
      stance.add(new Option('本宗赞成', 'yes'));
      stance.add(new Option('本宗反对', 'no'));
      const speaks = game.faction?.has_diplomatic_voice && members.some(f => f.id === game.faction.id);
      function refresh() {
        const motion = topic.value;
        const highest = Math.max(...members.map(f => f.places));
        const options = motion === 'aid' ? system.aid_offers : motion === 'invite' ? system.guest_sects
          : motion === 'amend' ? members.filter(f => f.id === record.counter)
          : motion === 'mediate' ? members.filter(f => highest - f.places >= 2) : members;
        target.replaceChildren();
        target.hidden = motion === 'rotate';
        if (!target.hidden) {
          for (const f of options) {
            const label = motion === 'aid' ? `${f.donor_name}济${f.name} · ${f.amount}灵石`
              : motion === 'invite' ? f.name + ' · ' + system.races[f.allegiance].name : f.name;
            target.add(new Option(label, f.id));
          }
        }
        const wait = motion === 'amend' ? 0 : record.next[motion] - game.player.age;
        button.disabled = wait > 0 || (!target.hidden && !options.length);
        button.dataset.councilUnavailable = button.disabled ? '1' : '0';
        hint.textContent = topics[motion][1] + (wait > 0 ? ` 再过${wait}年可重议。`
          : !target.hidden && !options.length ? ' 眼下没有合适的山门。' : '');
      }
      topic.onchange = refresh;
      form.onsubmit = event => {
        event.preventDefault();
        if (!button.disabled) submit({motion: topic.value, target: target.hidden ? '' : target.value,
          offer: topic.value === 'aid' ? [system.aid_offers[target.selectedIndex].donor, system.aid_offers[target.selectedIndex].amount] : null,
          race: race.id, world: system.world, expected_revision: game.updated_at,
          sect_vote: speaks ? stance.value === 'yes' : null,
          command_seq: system.council_seq, command_id: 'council-' + system.council_seq});
      };
      refresh();
      form.append(topic, target);
      if (speaks) form.append(stance);
      form.append(button, hint);
      section.append(form);
    }
    for (const meeting of [...record.recent].reverse()) {
      const fold = element('details');
      fold.append(element('summary', meeting.summary));
      for (const b of meeting.ballots) {
        fold.append(element('p', `${b.name} · ${b.abstain ? '留议' : b.yes ? '赞成' : '反对'}。 ${b.reason}。`));
      }
      section.append(fold);
    }
    if (section.children.length > 1) parent.append(section);
  }
  return {directory, meeting};
})();
