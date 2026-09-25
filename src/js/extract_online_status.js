(() => {
  const results = [];
  const seen = new Set();
  const items = document.querySelectorAll('[data-e2e="conversation-item"]');
  for (const item of items) {
    const titleEl = item.querySelector('[class="conversationConversationItemtitle"]');
    if (titleEl === null) continue;
    const fullName = titleEl.textContent.trim();
    if (!fullName || seen.has(fullName)) continue;
    seen.add(fullName);

    let name = fullName;
    name = name.replace(/^\d+分钟前\s*/, '');
    name = name.replace(/^\d+小时前\s*/, '');
    name = name.replace(/\d{1,2}[-/]\d{1,2}$/, '');
    name = name.trim();

    const avatar = item.querySelector('[class*="commonIMAvataravatarContainer"]');
    const dot = avatar ? avatar.querySelector('[class*="IMAvatarOnlineactiveDot"]') : null;
    const isOnline = dot !== null;

    let onlineText = '';
    const spans = item.querySelectorAll('span');
    for (const span of spans) {
      const t = span.textContent.trim();
      if (t.includes('在线') || t === '在线') { onlineText = t; break; }
    }

    const timeEl = item.querySelector('[class*="ConversationItemTagNextToTitletimeStr"]');
    const lastMsgTime = timeEl ? timeEl.textContent.trim() : '';

    const streakEl = item.querySelector('[class*="commonStreaknormalText"]');
    const streakText = streakEl ? streakEl.textContent.trim() : '';

    // 火苗状态：检查图标图片 URL 是否包含 "gray"
    const streakContainer = item.querySelector('[class*="commonStreakstreakContainer"]');
    const flameImg = streakContainer ? streakContainer.querySelector('img') : null;
    const flameSrc = flameImg ? (flameImg.src || '') : '';
    const renewed = flameSrc.length > 0 && !flameSrc.includes('gray');

    results.push({
      full_name: fullName,
      name: name,
      is_online: isOnline,
      online_status_text: onlineText,
      last_msg_time: lastMsgTime,
      streak_text: streakText,
      flame_src: flameSrc.split('/').pop(),
      renewed_today: renewed,
    });
  }
  return JSON.stringify(results);
})();
