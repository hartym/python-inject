'''Injectors are central part in C{python-inject}. They are used
by injection points (C{inject.attr}, C{inject.param}, etc.) to get bindings.
Injectors stores bindings in specific scopes which coordinate objects 
life-cycle.

An injector must be instantiated and registered before any injection point
is accessed. Only one injector can be registered at one time::

    >>> injector = Injector()
    >>> injector.register()
    
    >>> # or
    >>> injector = inject.create()

It can (and should) be used to configure application scoped
bindings, yet it delegates them to L{ApplicationScope}.

    >>> class A(object): pass
    >>> injector.bind(A, to=A())
    
    >>> # is equivalent to
    >>> scope = injector.get(ApplicationScope)
    >>> scope.bind(A, to=A())

Injection points use the L{Injector.get} method to get bindings for types.

    >>> class A(object): pass
    >>> a = A()
    >>> injector.bind(A to=a)
    >>> a2 = injector.get(A)
    >>> a is a2
    True

An injector by default creates and binds all scopes: L{ApplicationScope},
L{ThreadScope}, and L{RequestScope}. An injector cannot be used without
a bound application scope. Scopes are stored in a stack. By default,
they are accessed in this order: [application, thread, request].

'''
import logging

from inject.exc import InjectorAlreadyRegistered, NoInjectorRegistered, \
    NotBoundError, AutobindingFailed
from inject.log import configure_stdout_handler
from inject.scopes import ApplicationScope, ThreadScope, RequestScope


class Injector(object):
    
    '''C{Injector} provides injection points with bindings, delegates storing
    bindings to specific scopes which coordinate objects life-cycle.
    
    @warning: Not thread-safe.
    '''
    
    logger = logging.getLogger('inject.Injector')
    injector = None
    
    @classmethod
    def create(cls, autobind=True, echo=False):
        '''Create and register a new injector, and return it.
    
        @raise InjectorAlreadyRegistered: if another injector is already
            registered.
        '''
        injector = cls(autobind=autobind, echo=echo)
        injector.register()
        return injector
    
    @classmethod
    def cls_get_injector(cls):
        '''Return a registered injector or raise an exception.
        
        @raise NoInjectorRegistered: if no injector is registered.
        '''
        injector = cls.injector
        if injector is None:
            raise NoInjectorRegistered()
        
        return injector
    
    @classmethod
    def cls_register(cls, injector):
        '''Register an injector.
        
        @raise InjectorAlreadyRegistered: if another injector is already
            registered.
        '''
        another = cls.injector
        if another is not None:
            raise InjectorAlreadyRegistered(another)
        
        cls.injector = injector
        cls.logger.info('Registered %r.', injector)
    
    @classmethod
    def cls_unregister(cls, injector=None):
        '''Unregister a given injector, or any injector.'''
        if injector and cls.injector is not injector:
            return
        
        latter = cls.injector
        cls.injector = None
        cls.logger.info('Unregistered %r.', latter)
    
    @classmethod
    def cls_is_registered(cls, injector=None):
        '''Return true if a given injector, or any injector is registered.'''
        if injector:
            return cls.injector is injector
        
        return cls.injector is not None
    
    def __init__(self, autobind=True, echo=False):
        '''Create a new injector instance.
        
        @ivar autobind: Whether to autobind not bound types, 
            the default is true. 
        
        @ivar echo: When set to true creates a default C{inject} logger,
            adds an stdout handler, and sets the logging level to DEBUG.
            It affects all injectors.
        '''
        self.autobind = autobind
        if echo:
            configure_stdout_handler()
        
        self._init()
    
    def _init(self):
        '''Initialize the injector, create and bind ApplicationScope,
        and load the default configuration.
        '''
        self._scopes = {}
        self._scopes_stack = []
        
        self._app_scope = ApplicationScope()
        self.bind_scope(ApplicationScope, self._app_scope)
        
        self._default_config()
    
    def _default_config(self):
        '''Bind Injector to self, and create and bind ThreadScope
        and RequestScope.
        '''
        self.bind(Injector, to=self)
        
        thread_scope = ThreadScope()
        self.bind_scope(ThreadScope, thread_scope)
        
        reqscope = RequestScope()
        self.bind_scope(RequestScope, reqscope)
        
        self.logger.info('Loaded the default configuration.')
    
    def clear(self):
        '''Remove all bindings and scopes and reinit the injector.'''
        self._app_scope = None
        self._scopes = None
        self._scopes_stack = None
        
        self.logger.info('Cleared all bindings.')
        self._init()
    
    def __contains__(self, type):
        '''Return true if type is bound, else return False.'''
        return self.is_bound(type)
    
    def bind(self, type, to=None):
        '''Set a binding for a type in the application scope.'''
        if self.is_bound(type):
            self.unbind(type)
        
        self._app_scope.bind(type, to)
    
    def unbind(self, type):
        '''Unbind the first occurrence of a type in any scope.'''
        for scope in self._scopes_stack:
            if scope.is_bound(type):
                scope.unbind(type)
                return
    
    def is_bound(self, type):
        '''Return true if a type is bound in any scope, else return False.'''
        for scope in self._scopes_stack:
            if scope.is_bound(type):
                return True
        
        return False
    
    def get(self, type, none=False):
        '''Return a binding for a type, or autobind it, or raise an error.
        
        @param none: If true, returns None when no binding is found, does not
            raise an error.
        
        @raise NotBoundError: if there is no binding for a type,
            and autobind is false or the type is not callable.
        '''
        for scope in self._scopes_stack:
            if scope.is_bound(type) or scope.is_factory_bound(type):
                return scope.get(type)
        
        if self.autobind and callable(type):
            try:
                inst = type()
            except Exception, e:
                raise AutobindingFailed(type, e)
            
            self.bind(type, inst)
            return inst
        
        if none:
            return
        
        raise NotBoundError(type)
    
    #==========================================================================
    # Factories
    #==========================================================================
    
    def bind_factory(self, type, factory):
        '''Bind a type factory in the application scope
        (at first, unbind an existing one if present).
        '''
        if self.is_factory_bound(type):
            self.unbind_factory(type)
        
        self._app_scope.bind_factory(type, factory)
    
    def unbind_factory(self, type):
        '''Unbind the first occurrence of a type factory in any scope.'''
        for scope in self._scopes_stack:
            if scope.is_factory_bound(type):
                scope.unbind_factory(type)
                return
    
    def is_factory_bound(self, type):
        '''Return true if there is a bound type factory in any scope,
        else return false.
        '''
        for scope in self._scopes_stack:
            if scope.is_factory_bound(type):
                return True
        
        return False
    
    #==========================================================================
    # Scopes
    #==========================================================================
    
    def bind_scope(self, scope_type, scope):
        '''Bind a new scope, unbind another one if present.'''
        self.unbind_scope(scope_type)
        
        self.bind(scope_type, scope)
        self._scopes[scope_type] = scope
        self._scopes_stack.append(scope)
        
        self.logger.info('Bound scope %r to %r.', scope_type, scope)
    
    def unbind_scope(self, scope_type):
        '''Unbind a scope.'''
        if scope_type not in self._scopes:
            return
        
        self.unbind(scope_type)
        scope = self._scopes[scope_type]
        del self._scopes[scope_type]
        self._scopes_stack.remove(scope)
        
        self.logger.info('Unbound scope %r.', scope)
    
    def is_scope_bound(self, scope_type):
        '''Return true if a scope is bound.'''
        return scope_type in self._scopes
    
    #==========================================================================
    # Registering/unregistering
    #==========================================================================
    
    def register(self):
        '''Register this injector, or raise an error.
        
        @raise InjectorAlreadyRegistered: if another injector is already
            registered.
        '''
        self.cls_register(self)
    
    def unregister(self):
        '''Unregister this injector.'''
        self.cls_unregister(self)
    
    def is_registered(self):
        '''Return whether this injector is registered.'''
        return self.cls_is_registered(self)


def create(autobind=True, echo=False):
    '''Create and register a new injector, and return it.
    
    @raise InjectorAlreadyRegistered: if another injector is already registered.
    '''
    return Injector.create(autobind=autobind, echo=echo)


def get_instance(type, none=False):
    '''Return an instance from the registered injector.
    
    @raise NoInjectorRegistered: if no injector is registered.
    '''
    injector = Injector.cls_get_injector()
    return injector.get(type, none=none)


def register(injector):
    '''Register an injector.'''
    Injector.cls_register(injector)


def unregister(injector=None):
    '''Unregister an injector if given, or any injector.'''
    Injector.cls_unregister(injector)


def is_registered(injector=None):
    '''Return true if a given injector, or any injector is registered.'''
    return Injector.cls_is_registered(injector)
