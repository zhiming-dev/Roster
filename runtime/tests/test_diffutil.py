"""Unit tests for the git-diff summarizer (spec 004, T005). Pure — no git required."""

from roster.diffutil import FileDiff, summarize_diff

_MODIFIED = """\
diff --git a/src/util.py b/src/util.py
index 1234567..89abcde 100644
--- a/src/util.py
+++ b/src/util.py
@@ -1,3 +1,4 @@
 def a():
-    return 1
+    return 2
+    # note
 x = 1
"""

_ADDED = """\
diff --git a/new.py b/new.py
new file mode 100644
index 0000000..e69de29
--- /dev/null
+++ b/new.py
@@ -0,0 +1,2 @@
+print("hi")
+print("bye")
"""

_DELETED = """\
diff --git a/old.py b/old.py
deleted file mode 100644
index e69de29..0000000
--- a/old.py
+++ /dev/null
@@ -1,1 +0,0 @@
-print("gone")
"""

_RENAMED = """\
diff --git a/from.py b/to.py
similarity index 100%
rename from from.py
rename to to.py
"""


def test_empty_patch_yields_no_files():
    assert summarize_diff("") == []
    assert summarize_diff("   \n") == []


def test_modified_file_counts_additions_and_deletions():
    [f] = summarize_diff(_MODIFIED)
    assert f == FileDiff(path="src/util.py", status="modified", additions=2, deletions=1)


def test_added_file_is_detected():
    [f] = summarize_diff(_ADDED)
    assert f.path == "new.py" and f.status == "added"
    assert f.additions == 2 and f.deletions == 0


def test_deleted_file_uses_the_old_path():
    [f] = summarize_diff(_DELETED)
    assert f.path == "old.py" and f.status == "deleted"
    assert f.deletions == 1 and f.additions == 0


def test_renamed_file_uses_the_new_path():
    [f] = summarize_diff(_RENAMED)
    assert f.path == "to.py" and f.status == "renamed"
    assert f.additions == 0 and f.deletions == 0


def test_the_header_lines_are_not_counted_as_changes():
    # The +++ / --- header lines must not inflate the +/- counts.
    [f] = summarize_diff(_ADDED)
    assert f.additions == 2  # the two print() lines, not the '+++ b/new.py' header


def test_multiple_files_are_summarized_in_order():
    files = summarize_diff(_MODIFIED + _ADDED + _DELETED)
    assert [f.path for f in files] == ["src/util.py", "new.py", "old.py"]
    assert [f.status for f in files] == ["modified", "added", "deleted"]
