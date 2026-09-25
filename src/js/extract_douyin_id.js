// 从抖音个人主页中提取抖音号
() => {
    const text = document.body.innerText;

    const patterns = [
        /抖音号[:：\s]*(\d+)/,
        /抖音号[^\d]*(\d+)/,
        /(?:抖音号).{0,20}(\d{6,})/,
    ];

    for (const pattern of patterns) {
        const match = text.match(pattern);
        if (match) return match[1];
    }

    const allEls = document.querySelectorAll('*');
    for (const el of allEls) {
        const elText = el.innerText || el.textContent || '';
        if (elText.includes('抖音号')) {
            const match = elText.match(/(\d{6,})/);
            if (match) return match[1];
            let sibling = el.nextElementSibling;
            while (sibling) {
                const sibText = sibling.innerText || sibling.textContent || '';
                const sibMatch = sibText.match(/(\d{6,})/);
                if (sibMatch) return sibMatch[1];
                sibling = sibling.nextElementSibling;
            }
            const parent = el.parentElement;
            if (parent) {
                let parentSibling = parent.nextElementSibling;
                while (parentSibling) {
                    const psText = parentSibling.innerText ||
                        parentSibling.textContent || '';
                    const psMatch = psText.match(/(\d{6,})/);
                    if (psMatch) return psMatch[1];
                    parentSibling = parentSibling.nextElementSibling;
                }
            }
        }
    }

    return null;
}
