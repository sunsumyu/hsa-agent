"""临时脚本：清理 model_manager.py 中残留的 probe 代码"""
import pathlib, sys

sys.stdout.reconfigure(encoding='utf-8')

p = pathlib.Path("app/model_manager.py")
content = p.read_text(encoding="utf-8")

start_marker = "        # [V134.0 P3] Proactive Probe"
end_marker = "        return llm, m_id\n"

start_idx = content.find(start_marker)
end_idx = content.find(end_marker, start_idx) + len(end_marker)

if start_idx == -1:
    print("ERROR: start marker not found")
    exit(1)

new_block = (
    "        # [V134.0 P3] Proactive Probe -> FastCheck (no network ping)\n"
    "        if retry_count > 5:\n"
    "            raise ValueError(f'All nodes for role {role} are banned.')\n"
    "\n"
    "        state = endpoint_pool_manager.states.get(m_id)\n"
    "        if state and state.is_cooling:\n"
    "            logger.warning(f'[FastCheck] Node {m_id} cooling, switching.')\n"
    "            return await self.get_llm_by_role(role, retry_count + 1, config)\n"
    "\n"
    "        logger.debug(f'[FastCheck] Node {m_id} OK (memory check).')\n"
    "        return llm, m_id\n"
)

new_content = content[:start_idx] + new_block + content[end_idx:]
p.write_text(new_content, encoding="utf-8")
print(f"OK - replaced {end_idx - start_idx} chars. New file lines: {new_content.count(chr(10))}")
