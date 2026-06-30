import React from "react";
import { WordToken } from "./WordToken";
import { useSidebarStore } from "../store/sidebarStore";
import type { ArticleParagraph } from "../types";

interface Props {
  paragraphs: ArticleParagraph[];
  articleId: string;
  autoOpenSidebar: boolean;
}

export const ArticleBody: React.FC<Props> = ({ paragraphs, articleId, autoOpenSidebar }) => {
  const { close: closeSidebar } = useSidebarStore();

  const handleBodyClick = (e: React.MouseEvent) => {
    const target = e.target as HTMLElement;
    // Close sidebar if clicking on non-word area
    if (!target.closest("ruby")) {
      closeSidebar();
    }
  };

  return (
    <div
      className="leading-loose text-lg text-gray-800 font-serif"
      onClick={handleBodyClick}
    >
      {paragraphs.map((paragraph) => (
        <p key={paragraph.id} className="mb-5" data-sentence-index={paragraph.position}>
          {paragraph.tokens.map((token) => (
            <span key={token.index}>
              <WordToken
                token={token}
                articleId={articleId}
                articleParagraphId={paragraph.id}
                sentences={paragraph.sentences}
                autoOpenSidebar={autoOpenSidebar}
              />
            </span>
          ))}
        </p>
      ))}
    </div>
  );
};
