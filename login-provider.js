// Select only the observed INTL provider on the supported school's chooser page.
// Both provider links use the same HTML id, so never select by id alone.
(() => {
  if (location.origin !== 'https://learn.intl.zju.edu.cn') return null;
  const expected = 'https://learn.intl.zju.edu.cn/webapps/bb-zjdxsso-BBLEARN/index.jsp';
  for (const link of document.querySelectorAll('a.microsoft_login-link[href]')) {
    if (link.href === expected) return expected;
  }
  return null;
})()
