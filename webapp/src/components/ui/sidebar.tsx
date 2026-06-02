import * as React from "react";
import { PanelLeft } from "lucide-react";

const SIDEBAR_WIDTH = "17.5rem";
const SIDEBAR_WIDTH_MOBILE = "18rem";
const SIDEBAR_WIDTH_ICON = "4rem";
const SIDEBAR_KEYBOARD_SHORTCUT = "b";
const MOBILE_BREAKPOINT = 980;

type SidebarState = "expanded" | "collapsed";

type SidebarContextProps = {
  state: SidebarState;
  open: boolean;
  setOpen: (open: boolean | ((open: boolean) => boolean)) => void;
  openMobile: boolean;
  setOpenMobile: (open: boolean) => void;
  isMobile: boolean;
  toggleSidebar: () => void;
};

type SidebarProviderProps = React.ComponentProps<"div"> & {
  defaultOpen?: boolean;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
};

type SidebarProps = React.ComponentProps<"aside"> & {
  side?: "left" | "right";
  variant?: "sidebar" | "floating" | "inset";
  collapsible?: "offcanvas" | "icon" | "none";
};

type SidebarStyle = React.CSSProperties & {
  "--sidebar-width"?: string;
  "--sidebar-width-mobile"?: string;
  "--sidebar-width-icon"?: string;
};

type SidebarMenuButtonProps = React.ComponentProps<"button"> & {
  asChild?: boolean;
  isActive?: boolean;
  tooltip?: string;
};

type SidebarMenuButtonChildProps = React.HTMLAttributes<HTMLElement> & {
  "data-active"?: string;
};

const SidebarContext = React.createContext<SidebarContextProps | null>(null);

function cn(...classes: Array<string | undefined | null | false>) {
  return classes.filter(Boolean).join(" ");
}

function useIsMobile() {
  const [isMobile, setIsMobile] = React.useState(() => {
    if (typeof window === "undefined") {
      return false;
    }
    return window.innerWidth < MOBILE_BREAKPOINT;
  });

  React.useEffect(() => {
    const mediaQuery = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`);
    const onChange = () => setIsMobile(window.innerWidth < MOBILE_BREAKPOINT);
    onChange();
    mediaQuery.addEventListener("change", onChange);
    return () => mediaQuery.removeEventListener("change", onChange);
  }, []);

  return isMobile;
}

function useSidebar() {
  const context = React.useContext(SidebarContext);
  if (!context) {
    throw new Error("useSidebar must be used within a SidebarProvider.");
  }
  return context;
}

function SidebarProvider({
  defaultOpen = true,
  open: openProp,
  onOpenChange,
  className,
  style,
  children,
  ...props
}: SidebarProviderProps) {
  const isMobile = useIsMobile();
  const [openMobile, setOpenMobile] = React.useState(false);
  const [_open, _setOpen] = React.useState(defaultOpen);
  const open = openProp ?? _open;

  const setOpen = React.useCallback(
    (nextOpen: boolean | ((open: boolean) => boolean)) => {
      const openState = typeof nextOpen === "function" ? nextOpen(open) : nextOpen;
      if (onOpenChange) {
        onOpenChange(openState);
        return;
      }
      _setOpen(openState);
    },
    [onOpenChange, open]
  );

  const toggleSidebar = React.useCallback(() => {
    if (isMobile) {
      setOpenMobile((current) => !current);
      return;
    }
    setOpen((current) => !current);
  }, [isMobile, setOpen]);

  React.useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const isInputTarget = !!target && (
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable
      );
      if (isInputTarget) {
        return;
      }
      if (event.key.toLowerCase() === SIDEBAR_KEYBOARD_SHORTCUT && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        toggleSidebar();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [toggleSidebar]);

  React.useEffect(() => {
    if (!isMobile && openMobile) {
      setOpenMobile(false);
    }
  }, [isMobile, openMobile]);

  const state: SidebarState = open ? "expanded" : "collapsed";
  const contextValue = React.useMemo(
    () => ({
      state,
      open,
      setOpen,
      openMobile,
      setOpenMobile,
      isMobile,
      toggleSidebar,
    }),
    [state, open, setOpen, openMobile, isMobile, toggleSidebar]
  );

  const providerStyle: SidebarStyle = {
    "--sidebar-width": SIDEBAR_WIDTH,
    "--sidebar-width-mobile": SIDEBAR_WIDTH_MOBILE,
    "--sidebar-width-icon": SIDEBAR_WIDTH_ICON,
    ...(style as SidebarStyle),
  };

  return (
    <SidebarContext.Provider value={contextValue}>
      <div className={cn("uiSidebarProvider", className)} style={providerStyle} {...props}>
        {children}
      </div>
    </SidebarContext.Provider>
  );
}

function Sidebar({
  side = "left",
  variant = "sidebar",
  collapsible = "offcanvas",
  className,
  children,
  ...props
}: SidebarProps) {
  const { state, isMobile, openMobile, setOpenMobile } = useSidebar();
  const isOpen = isMobile ? openMobile : state === "expanded";

  return (
    <>
      <div
        className={cn("uiSidebarOverlay", isMobile && isOpen && "is-open")}
        onClick={() => setOpenMobile(false)}
        aria-hidden
      />
      <aside
        data-state={state}
        data-side={side}
        data-variant={variant}
        data-collapsible={collapsible}
        data-mobile={isMobile ? "true" : "false"}
        className={cn("uiSidebar", isOpen && "is-open", className)}
        {...props}
      >
        {children}
      </aside>
    </>
  );
}

function SidebarTrigger({ className, onClick, children, ...props }: React.ComponentProps<"button">) {
  const { toggleSidebar } = useSidebar();

  return (
    <button
      type="button"
      className={cn("sidebarTrigger", className)}
      onClick={(event) => {
        onClick?.(event);
        if (!event.defaultPrevented) {
          toggleSidebar();
        }
      }}
      {...props}
    >
      {children || (
        <>
          <PanelLeft size={18} />
          <span className="srOnly">Toggle Sidebar</span>
        </>
      )}
    </button>
  );
}

function SidebarRail({ className, ...props }: React.ComponentProps<"button">) {
  const { toggleSidebar } = useSidebar();
  return (
    <button
      type="button"
      className={cn("sidebarRail", className)}
      onClick={toggleSidebar}
      aria-label="Toggle Sidebar"
      {...props}
    />
  );
}

function SidebarInset({ className, ...props }: React.ComponentProps<"main">) {
  return <main className={cn("uiSidebarInset", className)} {...props} />;
}

function SidebarHeader({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("uiSidebarHeader", className)} {...props} />;
}

function SidebarFooter({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("uiSidebarFooter", className)} {...props} />;
}

function SidebarContent({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("uiSidebarContent", className)} {...props} />;
}

function SidebarGroup({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("uiSidebarGroup", className)} {...props} />;
}

function SidebarGroupLabel({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("uiSidebarGroupLabel", className)} {...props} />;
}

function SidebarGroupContent({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("uiSidebarGroupContent", className)} {...props} />;
}

function SidebarMenu({ className, ...props }: React.ComponentProps<"ul">) {
  return <ul className={cn("sidebarMenu", className)} {...props} />;
}

function SidebarMenuItem({ className, ...props }: React.ComponentProps<"li">) {
  return <li className={cn("sidebarMenuItem", className)} {...props} />;
}

function SidebarMenuButton({
  asChild = false,
  isActive = false,
  tooltip,
  className,
  children,
  ...props
}: SidebarMenuButtonProps) {
  const { state, isMobile } = useSidebar();
  const title = tooltip && !isMobile && state === "collapsed" ? tooltip : undefined;

  if (asChild && React.isValidElement(children)) {
    const child = children as React.ReactElement<SidebarMenuButtonChildProps>;
    return React.cloneElement(child, {
      ...(props as Partial<SidebarMenuButtonChildProps>),
      className: cn("sidebarMenuButton", className, child.props.className),
      "data-active": isActive ? "true" : "false",
      title: title || child.props.title,
    });
  }

  return (
    <button
      className={cn("sidebarMenuButton", className)}
      data-active={isActive ? "true" : "false"}
      title={title}
      {...props}
    >
      {children}
    </button>
  );
}

export {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger,
  useSidebar,
};
