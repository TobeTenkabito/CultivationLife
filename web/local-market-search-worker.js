/* User expressions run off the UI thread and may be terminated by the caller. */
self.onmessage = ({data}) => {
  try {
    const pattern = new RegExp(data.pattern, 'iu');
    self.postMessage({indices:data.names.flatMap((name,index) => pattern.test(name) ? [index] : [])});
  } catch (_) {
    self.postMessage({error:'正则表达式无效，请检查括号、字符组和重复符号。'});
  }
};
self.postMessage({ready:true});
