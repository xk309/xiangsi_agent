"""Operator CLI for reviewed UTF-8 documents; no automatic publication."""
import argparse
import asyncio
from pathlib import Path
from uuid import uuid4
from backend.agent.knowledge import KnowledgeModels
from backend.config import settings
from backend.database import connection


def split_document(text):
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    splitter = RecursiveCharacterTextSplitter(chunk_size=900, chunk_overlap=120,
        separators=['\n## ', '\n\n', '\n', '。', '；', ' ', ''])
    return splitter.split_text(text)


async def ingest(path, domain, title, version, source_uri, publish=False):
    if path.suffix.lower() not in ('.md', '.txt') or path.stat().st_size > 5_000_000:
        raise ValueError('仅接受5MB以内UTF-8 Markdown或TXT专业资料')
    chunks = split_document(path.read_text(encoding='utf-8-sig'))
    if not chunks:
        raise ValueError('文档为空')
    vectors = []
    if settings.knowledge_use_vectors:
        models = KnowledgeModels()
        for offset in range(0, len(chunks), 10):
            vectors.extend(await models.embed(chunks[offset:offset + 10]))
    document_id = str(uuid4())
    with connection() as database, database.cursor() as cursor:
        cursor.execute('''INSERT INTO knowledge_document
            (document_id,domain,title,source_uri,source_version,status,published_at)
            VALUES(%s,%s,%s,%s,%s,%s,CASE WHEN %s THEN now() ELSE NULL END)''',
            (document_id, domain, title, source_uri, version, 'PUBLISHED' if publish else 'DRAFT', publish))
        for index, chunk in enumerate(chunks):
            cursor.execute('''INSERT INTO knowledge_chunk
                (chunk_id,document_id,chunk_index,content,source_locator,embedding_model,embedding)
                VALUES(%s,%s,%s,%s,%s,%s,%s)''',
                (str(uuid4()), document_id, index, chunk, f'{title} / 片段{index + 1}',
                 settings.embedding_model if vectors else None, str(vectors[index]) if vectors else None))
    return {'document_id': document_id, 'chunks': len(chunks), 'status': 'PUBLISHED' if publish else 'DRAFT'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='导入专业资料；默认草稿，--publish表示操作者确认已审核。')
    parser.add_argument('path', type=Path)
    parser.add_argument('--domain', choices=['pollution', 'meteorology'], required=True)
    parser.add_argument('--title', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--source-uri', required=True)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    print(asyncio.run(ingest(args.path, args.domain, args.title, args.version, args.source_uri, args.publish)))
