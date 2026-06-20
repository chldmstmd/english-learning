import React from "react";
import { WordToken } from "./WordToken";
import { useSidebarStore } from "../store/sidebarStore";
import type { Token, Sentence } from "../types";

interface Props {
  tokens: Token[];
  sentences: Sentence[];
  articleId: string;
  autoOpenSidebar: boolean;
}

export const ArticleBody: React.FC<Props> = ({ tokens, sentences, articleId, autoOpenSidebar }) => {
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
      {tokens.map((token, i) => {
        const isSentenceStart = i === 0 || tokens[i - 1].sentence_index !== token.sentence_index;
        return (
          <span key={token.index} data-sentence-index={isSentenceStart ? token.sentence_index : undefined}>
            <WordToken
              token={token}
              articleId={articleId}
              sentences={sentences}
              autoOpenSidebar={autoOpenSidebar}
            />
          </span>
        );
      })}
    </div>
  );
};
