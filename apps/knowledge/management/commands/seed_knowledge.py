from django.core.management.base import BaseCommand
from django.db import transaction
from apps.knowledge.models import Course,Chapter,KnowledgePoint,KnowledgeRelation,KnowledgeChunk,KnowledgeCorrection

CATALOG = [
(1,'data','数据','能够被计算机识别、存储和处理的信息',1),
(1,'data-element','数据元素','数据处理的基本单位，由若干数据项组成',1),
(1,'data-item','数据项','数据元素不可再分的最小单位',1),
(1,'data-object','数据对象','性质相同的数据元素集合',1),
(1,'data-structure','数据结构','数据元素与特定关系的集合',1),
(1,'logical-structure','逻辑结构','集合、线性、树和图结构',1),
(1,'storage-structure','存储结构','顺序、链式、索引与散列存储',1),
(1,'adt','抽象数据类型','逻辑模型与操作的封装，独立于物理实现',2),
(1,'algorithm-properties','算法特性','有穷性、确定性、可行性、输入与输出',2),
(1,'time-complexity','时间复杂度','基本操作次数的渐近数量级',3),
(1,'space-complexity','空间复杂度','额外存储空间的渐近数量级',3),
(2,'linear-list','线性表','有限元素序列与一对一的前驱后继关系',4),
(2,'sequential-list','顺序表','连续存储单元表示的线性表',4),
(2,'random-access','随机存取','通过地址公式在常数时间访问元素',4),
(2,'linear-search','顺序查找','逐项比较，最坏时间 O(n)',4),
(2,'list-insert','顺序表插入','移动后续元素，最坏时间 O(n)',5),
(2,'list-delete','顺序表删除','移动后续元素，最坏时间 O(n)',5),
(2,'linked-list','单链表','节点由数据域和后继指针组成',5),
(2,'head-insert','头插法','每次插在头部，元素次序与输入相反',5),
(2,'tail-insert','尾插法','维护尾指针，保持输入顺序',5),
(2,'circular-list','循环链表','末节点回指头节点，形成环',6),
(2,'doubly-linked-list','双向链表','同时维护前驱与后继指针',6),
(3,'stack','栈','仅允许在栈顶插入和删除的线性表',7),
(3,'lifo','后进先出','最后压入元素最先弹出',7),
(3,'sequential-stack','顺序栈','数组与 top 指针，需检测溢出',7),
(3,'linked-stack','链栈','使用链表头作为栈顶',8),
(3,'queue','队列','队尾插入，队头删除',8),
(3,'fifo','先进先出','最先入队的元素最先出队',8),
(3,'circular-queue','循环队列','数组按模运算循环使用，避免假溢出',9),
(3,'linked-queue','链队列','队头与队尾指针实现 O(1) 操作',9),
(3,'queue-empty','队列判空','预留一格方案：front 等于 rear',9),
(3,'queue-full','队列判满','预留一格方案：(rear+1)%capacity 等于 front',9),
(3,'queue-operations','队列操作','入队、出队和长度的边界条件',9),
(4,'string','字符串','零个或多个字符的有限序列',11),
(4,'bf','BF 字符串匹配','失配后主串回退，最坏 O(nm)',12),
(4,'prefix-suffix','前缀与后缀','计算部分匹配表的基础，课程 KMP 补充概念',12),
(4,'next-array','next 数组','保存失配后的模式跳转位置',12),
(4,'kmp','KMP 字符串匹配','主串指针不回退，利用 next，时间 O(n+m)',12),
(4,'array','数组','相同类型元素与一组唯一确定位置的下标',13),
(4,'row-major','数组行优先','先逐行存储元素，地址偏移 i*n+j',13),
(4,'column-major','数组列优先','先逐列存储元素，地址偏移 j*m+i',13),
(4,'symmetric-matrix','对称矩阵压缩','只保存下三角及对角元素',13),
(4,'triangular-matrix','三角矩阵压缩','保存有效三角区与一个常数值',14),
(4,'tridiagonal-matrix','三对角矩阵','带内元素按行压缩共 3n-2 个，原文公式待勘误审核',14),
(4,'generalized-list','广义表','元素可为原子或子表，具有递归与共享结构',14)]
DEPENDENCIES = {'data-element':['data'],'data-item':['data-element'],'data-object':['data'],'data-structure':['data-element'],'logical-structure':['data-structure'],'storage-structure':['logical-structure'],'adt':['data-structure'],'time-complexity':['algorithm-properties'],'space-complexity':['algorithm-properties'],'linear-list':['logical-structure'],'sequential-list':['linear-list','storage-structure'],'random-access':['sequential-list'],'linear-search':['sequential-list'],'list-insert':['sequential-list'],'list-delete':['sequential-list'],'linked-list':['linear-list','storage-structure'],'head-insert':['linked-list'],'tail-insert':['linked-list'],'circular-list':['linked-list'],'doubly-linked-list':['linked-list'],'stack':['linear-list'],'lifo':['stack'],'sequential-stack':['stack','sequential-list'],'linked-stack':['stack','linked-list'],'queue':['linear-list'],'fifo':['queue'],'circular-queue':['queue','sequential-list'],'linked-queue':['queue','linked-list'],'queue-empty':['circular-queue'],'queue-full':['circular-queue'],'queue-operations':['queue-empty','queue-full'],'bf':['string'],'prefix-suffix':['bf'],'next-array':['prefix-suffix'],'kmp':['next-array','bf'],'array':['sequential-list'],'row-major':['array'],'column-major':['array'],'symmetric-matrix':['row-major'],'triangular-matrix':['row-major'],'tridiagonal-matrix':['row-major'],'generalized-list':['linked-list']}

class Command(BaseCommand):
    help = '幂等建立四章知识点、先修关系与待审核勘误，不创建学生记录'
    @transaction.atomic
    def handle(self,*args,**options):
        course,_=Course.objects.get_or_create(slug='data-structures',defaults={'name':'数据结构与算法'})
        for n,name in enumerate(['绪论','线性表','栈与队列','串、数组和广义表'],1):
            Chapter.objects.update_or_create(number=n,defaults={'course':course,'name':name})
        points = {}
        for i,(chapter,slug,name,desc,page) in enumerate(CATALOG):
            points[slug],_=KnowledgePoint.objects.update_or_create(slug=slug,defaults={'name':name,'chapter':chapter,'description':desc,'difficulty':2 if slug in ['kmp','tridiagonal-matrix','generalized-list'] else 1,'order':i,'source_page':page,'is_extension':slug=='prefix-suffix'})
        for slug,prereqs in DEPENDENCIES.items():
            points[slug].prerequisites.set([points[p] for p in prereqs])
            for p in prereqs: KnowledgeRelation.objects.get_or_create(source=points[p],target=points[slug],relation_type='prerequisite')
        for a,b in [('stack','queue'),('bf','kmp'),('row-major','column-major'),('sequential-list','linked-list')]:
            KnowledgeRelation.objects.get_or_create(source=points[a],target=points[b],relation_type='related')
        for page,needle,original,suggestion,verification in [
            (12,'返回位置 6','BF 示例匹配成功，返回位置 6','ababcabcacbab 中 abcac 从零基下标 5 开始；一基位置为 6。','Python: "ababcabcacbab".find("abcac") == 5'),
            (14,'2i + j - 3','三对角矩阵下标 k = 2i + j - 3','一基 i,j、零基压缩下标：k=2*i+j-3；原文前半式 2(i-1)+(j-i+1) 与后半式不等，应改为 2(i-1)+j-1。','枚举每行带内元素：[(1,1),(1,2),(2,1),...]; 2*i+j-3 对应下标 0..3n-3')]:
            chunk=KnowledgeChunk.objects.filter(page_number=page,content__contains=needle).first()
            if chunk: KnowledgeCorrection.objects.get_or_create(chunk=chunk,original_statement=original,defaults={'suggested_statement':suggestion,'reason':'原文下标约定或等式存在歧义，保留原文并等待教师审核。','verification':verification})
        self.stdout.write(f'知识点 {len(points)} 个；先修与关联关系 {KnowledgeRelation.objects.count()} 条。')
