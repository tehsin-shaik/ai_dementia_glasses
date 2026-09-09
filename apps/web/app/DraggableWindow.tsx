"use client";

import {
  createContext,
  CSSProperties,
  PointerEvent as ReactPointerEvent,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";

export type WindowPosition = {
  x: number;
  y: number;
};

type WindowStack = {
  bringToFront: (id: string) => void;
  getZIndex: (id: string, fallback: number) => number;
};

const WindowStackContext = createContext<WindowStack | null>(null);

export function DraggableWindowGroup({ children }: { children: ReactNode }) {
  const [order, setOrder] = useState<Record<string, number>>({});
  const nextZIndex = useRef(20);

  const bringToFront = useCallback((id: string) => {
    nextZIndex.current += 1;
    const zIndex = nextZIndex.current;
    setOrder((current) => ({ ...current, [id]: zIndex }));
  }, []);

  const getZIndex = useCallback((id: string, fallback: number) => order[id] ?? fallback, [order]);

  return (
    <WindowStackContext.Provider value={{ bringToFront, getZIndex }}>
      {children}
    </WindowStackContext.Provider>
  );
}

type DraggableWindowProps = {
  id: string;
  title: string;
  boundsRef: React.RefObject<HTMLElement | null>;
  initialPosition: WindowPosition;
  compactPosition?: WindowPosition;
  initialZIndex?: number;
  className?: string;
  children: ReactNode;
};

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(Math.max(value, minimum), Math.max(minimum, maximum));
}

export default function DraggableWindow({
  id,
  title,
  boundsRef,
  initialPosition,
  compactPosition,
  initialZIndex = 1,
  className = "",
  children,
}: DraggableWindowProps) {
  const stack = useContext(WindowStackContext);
  const windowRef = useRef<HTMLElement | null>(null);
  const titleBarRef = useRef<HTMLDivElement | null>(null);
  const hasDraggedRef = useRef(false);
  const dragRef = useRef<{ pointerId: number; offsetX: number; offsetY: number } | null>(null);
  const [position, setPosition] = useState<WindowPosition>(initialPosition);
  const [isDragging, setIsDragging] = useState(false);

  const clampToBounds = useCallback((nextPosition: WindowPosition): WindowPosition => {
    const bounds = boundsRef.current;
    const windowElement = windowRef.current;
    if (!bounds || !windowElement) {
      return nextPosition;
    }

    return {
      x: clamp(nextPosition.x, 0, bounds.clientWidth - windowElement.offsetWidth),
      y: clamp(nextPosition.y, 0, bounds.clientHeight - windowElement.offsetHeight),
    };
  }, [boundsRef]);

  useEffect(() => {
    const bounds = boundsRef.current;
    if (!bounds) {
      return;
    }

    const syncPosition = () => {
      setPosition((current) => {
        const compact = bounds.clientWidth < 900;
        const preferred = !hasDraggedRef.current && compact && compactPosition ? compactPosition : current;
        return clampToBounds(preferred);
      });
    };

    syncPosition();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(syncPosition);
    observer?.observe(bounds);
    window.addEventListener("resize", syncPosition);

    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", syncPosition);
    };
  }, [boundsRef, clampToBounds, compactPosition, initialPosition]);

  useEffect(() => {
    if (!isDragging) {
      return;
    }

    const previousUserSelect = document.body.style.userSelect;
    document.body.style.userSelect = "none";
    return () => {
      document.body.style.userSelect = previousUserSelect;
    };
  }, [isDragging]);

  function handlePointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    const bounds = boundsRef.current;
    const windowElement = windowRef.current;
    if (!bounds || !windowElement) {
      return;
    }

    const windowRect = windowElement.getBoundingClientRect();
    dragRef.current = {
      pointerId: event.pointerId,
      offsetX: event.clientX - windowRect.left,
      offsetY: event.clientY - windowRect.top,
    };
    hasDraggedRef.current = true;
    stack?.bringToFront(id);
    event.currentTarget.setPointerCapture(event.pointerId);
    event.preventDefault();
    setIsDragging(true);
  }

  function handlePointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    const drag = dragRef.current;
    const bounds = boundsRef.current;
    const windowElement = windowRef.current;
    if (!drag || drag.pointerId !== event.pointerId || !bounds || !windowElement) {
      return;
    }

    const boundsRect = bounds.getBoundingClientRect();
    setPosition(clampToBounds({
      x: event.clientX - boundsRect.left - drag.offsetX,
      y: event.clientY - boundsRect.top - drag.offsetY,
    }));
    event.preventDefault();
  }

  function finishDragging(event: ReactPointerEvent<HTMLDivElement>) {
    if (dragRef.current?.pointerId !== event.pointerId) {
      return;
    }
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    dragRef.current = null;
    setIsDragging(false);
  }

  function handleTitleBarKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      stack?.bringToFront(id);
    }
  }

  const style: CSSProperties = {
    left: `${position.x}px`,
    top: `${position.y}px`,
    zIndex: stack?.getZIndex(id, initialZIndex) ?? initialZIndex,
  };

  return (
    <article
      ref={windowRef}
      className={`draggable-window ${className} ${isDragging ? "is-dragging" : ""}`}
      style={style}
      aria-label={title}
    >
      <div
        ref={titleBarRef}
        className="window-title-bar"
        role="button"
        tabIndex={0}
        aria-label={`Drag ${title} window`}
        onKeyDown={handleTitleBarKeyDown}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={finishDragging}
        onPointerCancel={finishDragging}
      >
        <span className="window-lights" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
        <span className="window-title">{title}</span>
        <span className="window-grip" aria-hidden="true">⌟</span>
      </div>
      <div className="window-body">{children}</div>
    </article>
  );
}
