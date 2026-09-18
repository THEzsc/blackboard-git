import unittest
from finalize_export import parse_announcements, Node

EMPTY = '''<div id="containerdiv"><h2 class="hideoff">Content</h2>
<script>untrusted()</script><link href="/style.css">
<form id="announcementForm"><input name="course_id" value="_1234_1">
<input name="viewChoice" value="2"></form></div>'''

class AnnouncementTests(unittest.TestCase):
    def test_known_empty_course_view(self):
        self.assertEqual([],parse_announcements(EMPTY,'_1234_1').children)
    def test_normal_list(self):
        node=parse_announcements('<ul id="announcementList"><li>Hello</li></ul>','_1234_1')
        self.assertEqual(1,len([n for n in node.children if isinstance(n,Node)]))
    def test_unknown_error_login_and_wrong_course_rejected(self):
        for document in ('<html>Login</html>',EMPTY.replace('_1234_1','_9999_1'),EMPTY.replace('value="2"','value="1"'),EMPTY.replace('</div>','<p>Access denied</p></div>'),EMPTY.replace('</div>','<div></div></div>')):
            with self.subTest(document=document):
                with self.assertRaises(ValueError):parse_announcements(document,'_1234_1')

if __name__=='__main__':unittest.main()
