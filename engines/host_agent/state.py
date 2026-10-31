# engines/host_agent/state.py
"""
流转范围：仅host_agent包内部：section_ready_listener ↔ graph ↔ nodes；
不经过事件总线；不直接写磁盘。
"""
from typing import Any, TypedDict

from engines.common.events import HostDiscussionMessageEvent
from engines.contracts.judgement import SectionJudgement
from engines.host_agent.section_pair_store import SectionPairStore # 此处后补


class HostState(TypedDict, total=False):
    """Host LangGraph单次调用State；快照模式"""
    task_id: str                                                           # [持久 10轮执行过程,共享同一个对象]
    # 本次触发Graph执行的原始SECTION_READY事件载荷，事件总线回调拿到的dict
    event_payload: dict[str, Any]  # media/insight -> 发布的dict数据
    # 快照内的配对存储实例；本次Graph全部配对、就绪判断都操作该store
    section_pair_store: SectionPairStore # 存储证据对 -> 检查 是否凑齐了一对    [持久]
    # 已经完成的结构化裁决缓存；类型是公共契约SectionJudgement对象列表
    judgements: list[SectionJudgement]  # 存储研判结果  5                    [持久]
    # 本次Graph调用新产出的全部讨论事件对象；Graph结束，监听器取出批量publish总线
    discussion_events: list[HostDiscussionMessageEvent]  # 本次要发送给前端的
    # 本次generate节点生成的单条裁决；瞬时字段；仅本次调用generate→apply节点之间传递
    section_judgement: SectionJudgement | None # 本次研判结果

"""
    
    host 4个节点
    
    节点1: 接收外部单向传递的事件数据 (insight/media->数据->接收->SectionPairStore存储)
            
            -- 条件边: SectionPairStore检查是否凑齐一对  --
    
    节点2: 一个章节(media/insight凑齐)内容的研判 -> 研判的对象 一个 Judgement
    
    节点3: 收集和记录上一个节点的研判结果 Judgement -> judgements [1]
            
            -- 条件边: judgements len = 5
            
    节点4: 最终结果的汇总和落盘


 insight 一个章节 -> 触发一次 
 media   一个章节 -> 触发一次 
 
 10 
 
 1. insight -> 第一个章节的 -> 总结内容 body 
    host节点1 -> 第一个章节总结的内容对象 -> SectionPairStore [insight/1]
    END 
    
 2. insight -> 第二个章节的 -> 总结内容 body     
    host节点1 -> 第一个章节总结的内容对象 -> SectionPairStore [ insight/1 , insight/2]
    END  
 3. media  -> 第一个章节的 -> 总结内容 body 
    host节点1 -> 第一个章节总结的内容对象 -> SectionPairStore [insight/1 , insight/2 ,  media/1 ]
    host节点2 -> insight/media -> 第一个章节内容总结 -> Judgement
    host节点3 -> 第一个章节Judgement -> judgements [1] 
    END
    
 4. media -> 第二个章节的 -> 总结内容 body
    host节点1 -> 第二个章节总结的内容对象 -> SectionPairStore [insight/1 , insight/2 ,  media/1 , media/2]
    host节点2 -> insight/media -> 第二个章节内容总结 -> Judgement
    host节点3 -> 第二个章节Judgement -> judgements [1,2] 
    END 
 .... 5次
 
 10. insight -> 第五个章节的 -> 总结内容 body 
    host节点1 -> 第五个章节总结的内容对象 -> SectionPairStore [insight/1 , insight/2 ,  media/1 , media/2 , insight/3 , insight/4 , media/3 , media/4 , insight/5 ,  media/5 ]
    host节点2 -> insight/media -> 第五个章节内容总结 -> Judgement
    host节点3 -> 第五个章节Judgement -> judgements [1,2,3,4,5] 
    host节点4 -> 最终结果的汇总和落盘
    END
    
  
  state_dict:[task_id:state] = 循环的内存
  
  for 1 in range(10)
    
    if task_id in state_dict:
        state(
            task_id : state_dict.get(task_id),
            section_pair_store : state_dict.get(task_id).section_pair_store,
            judgements : state_dict.get(task_id).judgements,
        )
        
    result  = graph.invoke(state) 
    result本次执行后的state [task_id, section_pair_store, judgements , discussion_events] 
    state_dict[task_id] = result 
    
    discussion_events -> for -> 发送事件  1 [insight/media body]   [1 insight/media -> 凑齐 -> 研判 -> judgement 2] -> 
"""