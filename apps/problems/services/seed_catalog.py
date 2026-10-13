"""Original exercises derived from the four supplied chapters.

Cases include empty/singleton/boundary/wraparound inputs. Solutions are trusted
curriculum source, never evaluated inside the Django process. Remote execution
of the complete bank is performed by verify_problem_bank after configuration.
"""
from textwrap import dedent


def exercise(slug, title, difficulty, tags, description, inp, out, complexity, code, cases):
    return {"slug": slug, "title": title, "difficulty": difficulty, "tags": tags, "description": description,
            "input_description": inp, "output_description": out, "reference_complexity": complexity,
            "reference_solution": dedent(code).strip() + "\n", "cases": cases,
            "source": "据《数据结构与算法知识库文档》设计的原创训练；下标统一从 0 开始，题意优先"}


CATALOG = [
exercise("triangular-count", "01 · 双重循环的基本操作次数", 1, ["time-complexity", "algorithm-properties"],
    "外层 i 从 1 到 n，内层 j 从 1 到 i，每次执行一个基本操作。请输出操作总次数。0 ≤ n ≤ 10⁹。",
    "一个非负整数 n。", "输出一个整数。", "时间 O(1)，空间 O(1)", '''
    n = int(input())
    print(n * (n + 1) // 2)
    ''', [("4\n", "10\n"), ("0\n", "0\n"), ("1\n", "1\n"), ("1000000000\n", "500000000500000000\n")]),
exercise("halving-count", "02 · 折半循环与对数复杂度", 1, ["time-complexity"],
    "令 x = n，重复执行 x //= 2，直到 x = 0，输出执行次数。0 ≤ n ≤ 10¹⁸。",
    "一个非负整数 n。", "折半次数。", "时间 O(log n)，空间 O(1)", '''
    n = int(input())
    count = 0
    while n:
        n //= 2
        count += 1
    print(count)
    ''', [("8\n", "4\n"), ("0\n", "0\n"), ("1\n", "1\n"), ("15\n", "4\n")]),
exercise("list-insert", "03 · 顺序表插入", 1, ["sequential-list", "list-insert"],
    "在含 n 个整数的顺序表中，下标 p 处插入整数 x。0 ≤ p ≤ n ≤ 1000；p = n 表示尾插。",
    "首行 n p x；第二行 n 个整数，空表第二行为空。", "输出插入后的整数序列，以空格分隔。", "时间 O(n)，辅助空间 O(1)（不计输入）", '''
    n, p, x = map(int, input().split())
    a = list(map(int, input().split()))
    a.insert(p, x)
    print(*a)
    ''', [("3 1 9\n1 2 3\n", "1 9 2 3\n"), ("0 0 7\n\n", "7\n"), ("2 2 -1\n3 4\n", "3 4 -1\n"), ("2 0 9\n3 4\n", "9 3 4\n")]),
exercise("list-delete", "04 · 顺序表删除", 1, ["sequential-list", "list-delete"],
    "删除顺序表下标 p 处元素。1 ≤ n ≤ 1000，0 ≤ p < n。",
    "首行 n p；第二行 n 个整数。", "第一行被删除元素，第二行删除后的序列；空表输出空行。", "时间 O(n)，辅助空间 O(1)", '''
    n, p = map(int, input().split())
    a = list(map(int, input().split()))
    print(a.pop(p))
    print(*a)
    ''', [("3 1\n10 20 30\n", "20\n10 30\n"), ("1 0\n8\n", "8\n\n"), ("3 2\n1 2 3\n", "3\n1 2\n"), ("3 0\n1 2 3\n", "1\n2 3\n")]),
exercise("linear-search", "05 · 顺序查找与首次位置", 1, ["linear-search", "sequential-list"],
    "输出目标 x 在顺序表中第一次出现的下标；不存在则输出 -1。允许重复值和空表。",
    "首行 n x；第二行 n 个整数。0 ≤ n ≤ 1000。", "一个下标或 -1。", "时间 O(n)，空间 O(1)", '''
    n, x = map(int, input().split())
    a = list(map(int, input().split()))
    answer = -1
    for i, v in enumerate(a):
        if v == x:
            answer = i
            break
    print(answer)
    ''', [("5 3\n1 3 2 3 4\n", "1\n"), ("0 9\n\n", "-1\n"), ("3 4\n1 2 3\n", "-1\n"), ("1 -2\n-2\n", "0\n")]),
exercise("sequential-address", "06 · 随机存取的地址计算", 1, ["random-access", "sequential-list"],
    "连续存储表首元素地址为 base，每个元素占 width 字节。求下标 i 元素的地址。",
    "base width i，均为非负整数，width ≥ 1。", "目标地址。", "时间 O(1)，空间 O(1)", '''
    base, width, i = map(int, input().split())
    print(base + width * i)
    ''', [("1000 4 3\n", "1012\n"), ("0 1 0\n", "0\n"), ("100 8 0\n", "100\n"), ("100 8 99\n", "892\n")]),
exercise("linked-reverse", "07 · 单链表反转", 2, ["linked-list", "tail-insert"],
    "按照输入顺序构造单链表，并迭代修改 next 指针反转链表，输出反转后的值。建议先在算法实验室观察 prev、curr、next；仅输出一致无法证明内部确实使用链表。",
    "首行 n；第二行 n 个整数。0 ≤ n ≤ 1000。", "反转后序列，空表输出空行。", "时间 O(n)，辅助空间 O(1)（不计节点）", '''
    class Node:
        def __init__(self, value, next=None):
            self.value, self.next = value, next
    n = int(input())
    values = list(map(int, input().split()))
    head = tail = None
    for value in values:
        node = Node(value)
        if tail is None:
            head = node
        else:
            tail.next = node
        tail = node
    prev, curr = None, head
    while curr is not None:
        nxt = curr.next
        curr.next = prev
        prev, curr = curr, nxt
    values = []
    while prev is not None:
        values.append(prev.value)
        prev = prev.next
    print(*values)
    ''', [("4\n1 2 3 4\n", "4 3 2 1\n"), ("0\n\n", "\n"), ("1\n9\n", "9\n"), ("5\n-1 2 2 0 7\n", "7 0 2 2 -1\n")]),
exercise("head-insert", "08 · 头插法建立单链表", 1, ["linked-list", "head-insert"],
    "依次读入 n 个整数，每个新节点插入到当前表头之前，输出最终链表的值。",
    "首行 n；第二行 n 个整数。0 ≤ n ≤ 1000。", "最终序列。", "时间 O(n)，节点空间 O(n)", '''
    class Node:
        def __init__(self, v, nxt):
            self.value, self.next = v, nxt
    n = int(input())
    head = None
    for v in map(int, input().split()):
        head = Node(v, head)
    result = []
    while head:
        result.append(head.value)
        head = head.next
    print(*result)
    ''', [("3\n1 2 3\n", "3 2 1\n"), ("0\n\n", "\n"), ("1\n0\n", "0\n"), ("4\n2 2 -1 0\n", "0 -1 2 2\n")]),
exercise("josephus", "09 · 循环链表与约瑟夫环", 2, ["circular-list"],
    "n 个人编号 0 至 n-1 围成一圈，从 0 开始数到 k 的人退出，下一人重新从 1 数。输出最后剩下的编号。1 ≤ n ≤ 10⁵，1 ≤ k ≤ 10⁹。",
    "n k。", "最后编号。", "时间 O(n)，空间 O(1)", '''
    n, k = map(int, input().split())
    survivor = 0
    for size in range(2, n + 1):
        survivor = (survivor + k) % size
    print(survivor)
    ''', [("5 3\n", "3\n"), ("1 999\n", "0\n"), ("7 2\n", "6\n"), ("10 1\n", "9\n")]),
exercise("bracket-stack", "10 · 栈与括号匹配", 2, ["stack", "lifo", "sequential-stack"],
    "判断只含 ()[]{} 的一行字符串是否正确匹配；空串视为匹配。长度 ≤ 2000。",
    "一行括号串。", "匹配输出 YES，否则 NO。", "时间 O(n)，空间 O(n)", '''
    s = input()
    stack = []
    pairs = {')': '(', ']': '[', '}': '{'}
    ok = True
    for ch in s:
        if ch in '([{':
            stack.append(ch)
        elif not stack or stack.pop() != pairs[ch]:
            ok = False
            break
    print('YES' if ok and not stack else 'NO')
    ''', [("([]{})\n", "YES\n"), ("\n", "YES\n"), ("([)]\n", "NO\n"), (")\n", "NO\n"), ("((\n", "NO\n")]),
exercise("stack-operations", "11 · 顺序栈模拟", 1, ["stack", "sequential-stack", "lifo"],
    "容量 capacity 的顺序栈，PUSH x 时若满输出 FULL，成功不输出；POP 输出栈顶值，空栈输出 EMPTY。",
    "首行 capacity q；后续 q 行 PUSH x 或 POP。1 ≤ capacity ≤ 1000。", "每个出栈或失败操作一行。", "时间 O(q)，空间 O(capacity)", '''
    capacity, q = map(int, input().split())
    stack = []
    for _ in range(q):
        op = input().split()
        if op[0] == 'PUSH':
            if len(stack) == capacity:
                print('FULL')
            else:
                stack.append(int(op[1]))
        else:
            print(stack.pop() if stack else 'EMPTY')
    ''', [("2 5\nPUSH 1\nPUSH 2\nPUSH 3\nPOP\nPOP\n", "FULL\n2\n1\n"), ("1 2\nPOP\nPOP\n", "EMPTY\nEMPTY\n"), ("1 3\nPUSH -1\nPOP\nPOP\n", "-1\nEMPTY\n"), ("3 0\n", "\n")]),
exercise("circular-queue", "12 · 循环队列与回绕", 2, ["queue", "circular-queue", "queue-empty", "queue-full", "queue-operations", "fifo"],
    "数组容量 capacity，牺牲一格，实际可存 capacity-1 个元素。ENQUEUE x：满时输出 FULL，成功不输出；DEQUEUE：输出队头或 EMPTY。front 指向队头前一格，rear 指向队尾。",
    "首行 capacity q；后续 q 行 ENQUEUE x 或 DEQUEUE。2 ≤ capacity ≤ 1000。", "失败入队及所有出队结果，每条一行。", "时间 O(q)，空间 O(capacity)", '''
    capacity, q = map(int, input().split())
    a = [None] * capacity
    front = rear = 0
    for _ in range(q):
        op = input().split()
        if op[0] == 'ENQUEUE':
            if (rear + 1) % capacity == front:
                print('FULL')
            else:
                rear = (rear + 1) % capacity
                a[rear] = int(op[1])
        elif front == rear:
            print('EMPTY')
        else:
            front = (front + 1) % capacity
            print(a[front])
    ''', [("3 8\nENQUEUE 1\nENQUEUE 2\nENQUEUE 3\nDEQUEUE\nENQUEUE 3\nDEQUEUE\nDEQUEUE\nDEQUEUE\n", "FULL\n1\n2\n3\nEMPTY\n"), ("2 3\nDEQUEUE\nENQUEUE 9\nDEQUEUE\n", "EMPTY\n9\n"), ("2 3\nENQUEUE 1\nENQUEUE 2\nDEQUEUE\n", "FULL\n1\n"), ("4 0\n", "\n")]),
exercise("linked-queue", "13 · 链队列 FIFO 模拟", 1, ["linked-queue", "fifo", "queue-operations"],
    "模拟无容量限制的链队列。ENQUEUE x 入队；DEQUEUE 输出队头，队空输出 EMPTY。注意最后一个元素出队后队尾也应复位。",
    "首行操作数 q，随后 q 行操作。q ≤ 2000。", "每次出队一行。", "时间 O(q)，空间 O(q)", '''
    from collections import deque
    q = int(input())
    a = deque()
    for _ in range(q):
        op = input().split()
        if op[0] == 'ENQUEUE':
            a.append(int(op[1]))
        else:
            print(a.popleft() if a else 'EMPTY')
    ''', [("5\nENQUEUE 1\nENQUEUE 2\nDEQUEUE\nDEQUEUE\nDEQUEUE\n", "1\n2\nEMPTY\n"), ("3\nDEQUEUE\nENQUEUE 0\nDEQUEUE\n", "EMPTY\n0\n"), ("4\nENQUEUE 1\nDEQUEUE\nENQUEUE 2\nDEQUEUE\n", "1\n2\n"), ("0\n", "\n")]),
exercise("bf-match", "14 · BF 字符串匹配", 1, ["string", "bf"],
    "用 BF 算法寻找模式串在主串中首次出现的 0 起始下标，不存在输出 -1，空模式输出 0。字符串可含空格；单行长度 ≤ 1000。",
    "第一行主串 S，第二行模式串 T。", "首次匹配位置。", "最坏时间 O(nm)，空间 O(1)", '''
    s, t = input(), input()
    answer = -1
    for i in range(len(s) - len(t) + 1):
        j = 0
        while j < len(t) and s[i + j] == t[j]:
            j += 1
        if j == len(t):
            answer = i
            break
    print(answer)
    ''', [("ababcabcacbab\nabcac\n", "5\n"), ("abc\n\n", "0\n"), ("aaaa\naa\n", "0\n"), ("abc\nd\n", "-1\n"), ("\na\n", "-1\n")]),
exercise("kmp-next", "15 · KMP 的 next 数组", 2, ["prefix-suffix", "next-array"],
    "计算教材约定的 next 数组：next[0] = -1；j > 0 时 next[j] 为 T[:j] 的最长相等真前后缀长度。空模式输出空行。",
    "一行模式串，长度 ≤ 1000。", "空格分隔的 next 数组。", "时间 O(m)，空间 O(m)", '''
    t = input()
    nxt = [-1] * len(t)
    i, j = 0, -1
    while i < len(t) - 1:
        if j == -1 or t[i] == t[j]:
            i, j = i + 1, j + 1
            nxt[i] = j
        else:
            j = nxt[j]
    print(*nxt)
    ''', [("abcac\n", "-1 0 0 0 1\n"), ("aaaa\n", "-1 0 1 2\n"), ("a\n", "-1\n"), ("\n", "\n"), ("ababaca\n", "-1 0 0 1 2 3 0\n")]),
exercise("kmp-match", "16 · KMP 主串指针不回退", 3, ["kmp", "next-array", "string"],
    "实现 KMP 首次模式匹配，输出 0 起始下标，不存在为 -1，空模式为 0。输入长度 ≤ 10⁵。输出一致只能验证结果，复杂度需结合代码分析。",
    "第一行主串，第二行模式串。", "首次匹配位置。", "时间 O(n+m)，空间 O(m)", '''
    s, t = input(), input()
    nxt = [-1] * len(t)
    i, j = 0, -1
    while i < len(t) - 1:
        if j == -1 or t[i] == t[j]:
            i, j = i + 1, j + 1
            nxt[i] = j
        else:
            j = nxt[j]
    i = j = 0
    while i < len(s) and j < len(t):
        if j == -1 or s[i] == t[j]:
            i, j = i + 1, j + 1
        else:
            j = nxt[j]
    print(i - j if j == len(t) else -1)
    ''', [("ababcabcacbab\nabcac\n", "5\n"), ("aaaaab\naaab\n", "2\n"), ("abc\n\n", "0\n"), ("abc\nabd\n", "-1\n"), ("\nabc\n", "-1\n")]),
exercise("array-address", "17 · 二维数组行列优先地址", 1, ["array", "row-major", "column-major"],
    "m×n 数组 A，下标均从 0 开始，首地址 base，元素宽度 width。求 A[i][j] 的行优先与列优先地址。",
    "m n base width i j，1 ≤ m,n；0 ≤ i < m，0 ≤ j < n。", "一行两个地址，先行优先后列优先。", "时间 O(1)，空间 O(1)", '''
    m, n, base, width, i, j = map(int, input().split())
    print(base + (i * n + j) * width, base + (j * m + i) * width)
    ''', [("3 4 1000 4 1 2\n", "1024 1028\n"), ("1 1 0 8 0 0\n", "0 0\n"), ("2 3 100 2 1 2\n", "110 110\n"), ("3 2 10 1 0 1\n", "11 13\n")]),
exercise("symmetric-index", "18 · 对称矩阵压缩下标", 2, ["symmetric-matrix"],
    "按行保存 n 阶对称矩阵下三角（含主对角线）。求 A[i][j] 在压缩数组的 0 起始下标。i,j 使用 0 起始。",
    "n i j，0 ≤ i,j < n。", "压缩下标。", "时间 O(1)，空间 O(1)", '''
    n, i, j = map(int, input().split())
    if i < j:
        i, j = j, i
    print(i * (i + 1) // 2 + j)
    ''', [("3 0 2\n", "3\n"), ("1 0 0\n", "0\n"), ("4 3 3\n", "9\n"), ("3 2 1\n", "4\n")]),
exercise("upper-triangle-index", "19 · 上三角矩阵压缩下标", 2, ["triangular-matrix"],
    "按行保存 n 阶上三角矩阵的主对角线及以上元素，并在末尾追加下三角公共常数。求 A[i][j] 的压缩下标，i,j 从 0 开始。",
    "n i j，0 ≤ i,j < n。", "压缩下标，下三角全部指向公共常数槽。", "时间 O(1)，空间 O(1)", '''
    n, i, j = map(int, input().split())
    print(i * (2 * n - i + 1) // 2 + j - i if i <= j else n * (n + 1) // 2)
    ''', [("3 1 2\n", "4\n"), ("3 2 0\n", "6\n"), ("1 0 0\n", "0\n"), ("4 3 3\n", "9\n")]),
exercise("tridiagonal-index", "20 · 三对角矩阵的紧凑下标", 2, ["tridiagonal-matrix"],
    "按行依次保存 |i-j| ≤ 1 的三对角矩阵元素（包括带内的零）。输入使用 0 起始下标。带外返回 -1。推导时注意首尾行各少一个元素。",
    "n i j，1 ≤ n，0 ≤ i,j < n。", "压缩下标或 -1。", "时间 O(1)，空间 O(1)", '''
    n, i, j = map(int, input().split())
    if abs(i - j) > 1:
        print(-1)
    elif n == 1:
        print(0)
    else:
        print(2 * i + j)
    ''', [("4 2 1\n", "5\n"), ("4 3 3\n", "9\n"), ("4 0 3\n", "-1\n"), ("1 0 0\n", "0\n"), ("2 1 0\n", "2\n")]),
exercise("generalized-depth", "21 · 广义表深度", 2, ["generalized-list"],
    "计算广义表括号嵌套深度，原子用单字母表示，空表 () 深度为 1。输入保证合法，无递归自引用；长度 ≤ 2000。",
    "一行如 (a,(b,c),()) 的广义表。", "最大嵌套深度。", "时间 O(n)，空间 O(1)", '''
    s = input()
    depth = answer = 0
    for ch in s:
        if ch == '(':
            depth += 1
            answer = max(answer, depth)
        elif ch == ')':
            depth -= 1
    print(answer)
    ''', [("(a,(b,(c,d)),e)\n", "3\n"), ("()\n", "1\n"), ("(a,b,c)\n", "1\n"), ("((()))\n", "3\n")]),
]
