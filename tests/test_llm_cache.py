from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

from tarvo_close.llm_cache import ResponseCache, canonical


class CacheTests(unittest.TestCase):
    def test_canonical_is_order_independent(self):
        self.assertEqual(canonical({'b':1,'a':[1,2]}),canonical({'a':[1,2],'b':1}))
        self.assertEqual(canonical({'a':'ção'}),'{"a":"ção"}')

    def test_key_changes_with_each_part(self):
        cache = ResponseCache('x')
        base = cache.key('v1','m1',{'campo':1})
        self.assertEqual(base,cache.key('v1','m1',{'campo':1}))
        self.assertEqual(len(base),64)
        for other in (cache.key('v2','m1',{'campo':1}), cache.key('v1','m2',{'campo':1}), cache.key('v1','m1',{'campo':2})):
            self.assertNotEqual(base,other)

    def test_put_and_get(self):
        with TemporaryDirectory() as directory:
            cache = ResponseCache(Path(directory)/'novo'/'llm')
            self.assertIsNone(cache.get('abc'))
            cache.put('abc',{'data':{'x':1}})
            self.assertEqual(cache.get('abc'),{'data':{'x':1}})

    def test_corrupt_entry_is_a_miss(self):
        with TemporaryDirectory() as directory:
            (Path(directory)/'abc.json').write_text('{',encoding='utf-8')
            self.assertIsNone(ResponseCache(directory).get('abc'))


if __name__ == '__main__':
    unittest.main()
