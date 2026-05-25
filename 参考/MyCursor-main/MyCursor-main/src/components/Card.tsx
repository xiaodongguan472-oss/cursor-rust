import React, { memo, CSSProperties } from "react";

interface CardProps {
  children: React.ReactNode;
  className?: string;
  style?: CSSProperties;
  hover?: boolean;
  onClick?: () => void;
}

interface CardHeaderProps {
  children: React.ReactNode;
  className?: string;
  style?: CSSProperties;
}

interface CardContentProps {
  children: React.ReactNode;
  className?: string;
  style?: CSSProperties;
}

interface CardFooterProps {
  children: React.ReactNode;
  className?: string;
  style?: CSSProperties;
}

const CardBase: React.FC<CardProps> = memo(({
  children,
  className = "",
  style,
  hover = false,
  onClick
}) => {
  const cardStyle: CSSProperties = {
    backgroundColor: 'var(--bg-primary)',
    borderRadius: 'var(--border-radius-lg)',
    boxShadow: 'var(--shadow-light)',
    transition: 'all 0.2s ease',
    backdropFilter: 'blur(var(--backdrop-blur))',
    WebkitBackdropFilter: 'blur(var(--backdrop-blur))',
    ...style,
  };

  return (
    <div
      className={`${hover ? 'cursor-pointer' : ''} ${className}`}
      style={cardStyle}
      onClick={onClick}
      onMouseEnter={(e) => {
        if (hover) {
          e.currentTarget.style.transform = 'translateY(-2px)';
          e.currentTarget.style.boxShadow = 'var(--shadow-medium)';
        }
      }}
      onMouseLeave={(e) => {
        if (hover) {
          e.currentTarget.style.transform = 'translateY(0)';
          e.currentTarget.style.boxShadow = 'var(--shadow-light)';
        }
      }}
    >
      {children}
    </div>
  );
});

CardBase.displayName = "Card";

const Card = CardBase as typeof CardBase & {
  Header: React.FC<CardHeaderProps>;
  Content: React.FC<CardContentProps>;
  Footer: React.FC<CardFooterProps>;
};

const CardHeader: React.FC<CardHeaderProps> = memo(({
  children,
  className = "",
  style,
}) => {
  return (
    <div
      className={`px-4 py-3 ${className}`}
      style={{
        borderBottom: '1px solid var(--border-primary)',
        borderTopLeftRadius: 'var(--border-radius-lg)',
        borderTopRightRadius: 'var(--border-radius-lg)',
        ...style,
      }}
    >
      {children}
    </div>
  );
});

CardHeader.displayName = "CardHeader";

const CardContent: React.FC<CardContentProps> = memo(({
  children,
  className = "",
  style,
}) => {
  return (
    <div
      className={`px-4 py-3 ${className}`}
      style={style}
    >
      {children}
    </div>
  );
});

CardContent.displayName = "CardContent";

const CardFooter: React.FC<CardFooterProps> = memo(({
  children,
  className = "",
  style,
}) => {
  return (
    <div
      className={`px-4 py-3 ${className}`}
      style={{
        borderTop: '1px solid var(--border-primary)',
        borderBottomLeftRadius: 'var(--border-radius-lg)',
        borderBottomRightRadius: 'var(--border-radius-lg)',
        ...style,
      }}
    >
      {children}
    </div>
  );
});

CardFooter.displayName = "CardFooter";

Card.Header = CardHeader;
Card.Content = CardContent;
Card.Footer = CardFooter;

export default Card;
