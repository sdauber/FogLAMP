# -*- coding: utf-8 -*-

# FOGLAMP_BEGIN
# See: http://foglamp.readthedocs.io/
# FOGLAMP_END

"""FogLAMP Scheduler module"""

import asyncio
import collections
import datetime
import logging
import math
import time
import uuid
from enum import IntEnum
from typing import Optional

import aiopg.sa
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg_types

from foglamp import logger


__author__ = "Terris Linenbach"
__copyright__ = "Copyright (c) 2017 OSIsoft, LLC"
__license__ = "Apache 2.0"
__version__ = "${VERSION}"

# Module attributes
_CONNECTION_STRING = "dbname='foglamp'"


class PausedError(RuntimeError):
    pass


class TaskRunningError(RuntimeError):
    pass


class TaskQueuedError(RuntimeError):
    pass


class ScheduleNotFoundError(ValueError):
    def __init__(self, schedule_id: uuid.UUID, *args):
        self.schedule_id = schedule_id
        super(ValueError, self).__init__(
            "Schedule not found: {}".format(schedule_id), *args)


class Schedule(object):
    """Schedule base class"""
    __slots__ = ['schedule_id', 'name', 'process_name', 'exclusive', 'repeat']

    def __init__(self):
        self.schedule_id = None
        """uuid.UUID"""
        self.name = None
        """str"""
        self.exclusive = True
        """bool"""
        self.repeat = None
        """"datetime.timedelta"""
        self.process_name = None
        """str"""


class IntervalSchedule(Schedule):
    """Interval schedule"""
    pass


class TimedSchedule(Schedule):
    """Timed schedule"""
    __slots__ = ['time', 'day']

    def __init__(self):
        super().__init__()
        self.time = None
        """int"""
        self.day = None
        """int from 1 (Monday) to 7 (Sunday)"""


class ManualSchedule(Schedule):
    """A schedule that is run manually"""
    pass


class StartUpSchedule(Schedule):
    """A schedule that is run when the scheduler starts"""
    pass


class Scheduler(object):
    """FogLAMP Task Scheduler

    Starts and tracks 'tasks' that run periodically,
    start-up, and/or manually.

    Schedules specify when to start and restart Tasks. A Task
    is an operating system process. ScheduleProcesses
    specify process/command name and parameters.

    Most methods are coroutines and use the default
    event loop to create tasks.

    This class does not use threads.

    Usage:
        - Call :meth:`start`
        - Wait
        - Call :meth:`stop`
    """

    # TODO: Methods that accept a schedule and look in _schedule_execution
    # should accept _schedule_execution to avoid the lookup or just
    # accept _schedule_execution if a _Schedule reference is added to
    # it (requires converting _Schedule to class)

    # TODO: Change _process_scripts to _processes containing
    # _Process objects. Then add process reference to _Schedule
    # to avoid script lookup.

    class _ScheduleType(IntEnum):
        """Enumeration for schedules.schedule_type"""
        STARTUP = 1
        TIMED = 2
        INTERVAL = 3
        MANUAL = 4

    class _TaskState(IntEnum):
        """Enumeration for tasks.task_state"""
        RUNNING = 1
        COMPLETE = 2
        CANCELED = 3
        INTERRUPTED = 4

    # TODO: This will be turned into a class so it is mutable
    _ScheduleRow = collections.namedtuple(
        'ScheduleRow',
        'id name type time day repeat repeat_seconds exclusive process_name')
    """Represents a row in the schedules table"""

    class _TaskProcess(object):
        """Tracks a running task with some flags"""
        __slots__ = ['process']

        def __init__(self):
            self.process = None
            """asyncio.subprocess.Process"""

    class _ScheduleExecution(object):
        """Tracks information about schedules"""
        __slots__ = ['next_start_time', 'task_processes', 'start_now']

        def __init__(self):
            self.next_start_time = None
            """When to next start a task for the schedule"""
            self.task_processes = dict()
            """dict of task id to _TaskProcess"""
            self.start_now = False
            """True when a task is queued to start via :meth:`start_task`"""

    # Constant class attributes
    _HOUR_SECONDS = 3600
    _DAY_SECONDS = 3600*24
    _WEEK_SECONDS = 3600*24*7
    _MAX_SLEEP = 9999999
    _ONE_HOUR = datetime.timedelta(hours=1)
    _ONE_DAY = datetime.timedelta(days=1)
    """When there is nothing to do, sleep for this number of seconds (forever)"""

    # Mostly constant class attributes
    _scheduled_processes_tbl = None  # type: sa.Table
    _schedules_tbl = None  # type: sa.Table
    _tasks_tbl = None  # type: sa.Table
    _logger = None

    def __init__(self):
        """Constructor"""

        """Class attributes"""
        if not self._logger:
            # self._logger = logger.setup(__name__, destination=logger.CONSOLE, level=logging.DEBUG)
            self._logger = logger.setup(__name__, level=logging.DEBUG)
            # self._logger = logger.setup(__name__)

        if not self._schedules_tbl:
            metadata = sa.MetaData()

            self._schedules_tbl = sa.Table(
                'schedules',
                metadata,
                sa.Column('id', pg_types.UUID),
                sa.Column('schedule_name', sa.types.VARCHAR(20)),
                sa.Column('process_name', sa.types.VARCHAR(20)),
                sa.Column('schedule_type', sa.types.SMALLINT),
                sa.Column('schedule_time', sa.types.TIME),
                sa.Column('schedule_day', sa.types.SMALLINT),
                sa.Column('schedule_interval', sa.types.Interval),
                sa.Column('exclusive', sa.types.BOOLEAN))

            self._tasks_tbl = sa.Table(
                'tasks',
                metadata,
                sa.Column('id', pg_types.UUID),
                sa.Column('process_name', sa.types.VARCHAR(20)),
                sa.Column('state', sa.types.INT),
                sa.Column('start_time', sa.types.TIMESTAMP),
                sa.Column('end_time', sa.types.TIMESTAMP),
                sa.Column('pid', sa.types.INT),
                sa.Column('exit_code', sa.types.INT),
                sa.Column('reason', sa.types.VARCHAR(255)))

            self._scheduled_processes_tbl = sa.Table(
                'scheduled_processes',
                metadata,
                sa.Column('name', pg_types.VARCHAR(20)),
                sa.Column('script', pg_types.JSONB))

        # Instance attributes
        self._start_time = None
        """When the scheduler started"""
        self._paused = False
        """When True, the scheduler will not start any new tasks"""
        self._process_scripts = dict()
        """Dictionary of schedules.id to script"""
        self._schedules = dict()
        """Dictionary of schedules.id to immutable _Schedule"""
        self._schedule_executions = dict()
        """Dictionary of schedules.id to _ScheduleExecution"""
        self._active_task_count = 0
        """Number of active tasks"""
        self._main_sleep_task = None
        """Coroutine that sleeps in the main loop"""

    async def stop(self):
        """Attempts to stop the scheduler

        Sends TERM signal to all running tasks. Does not wait for tasks to stop.

        Prevents any new tasks from starting. This can be undone by setting the
        _paused attribute to False.

        Raises TimeoutError:
            A task is still running. Wait and try again.
        """
        self._logger.info("Stop requested")

        # Stop the main loop
        self._paused = True
        self._resume_check_schedules()

        # Can not iterate over _schedule_executions - it can change mid-iteration
        for schedule_id in list(self._schedule_executions.keys()):
            try:
                schedule_execution = self._schedule_executions[schedule_id]
            except KeyError:
                continue

            for task_id in list(schedule_execution.task_processes):
                try:
                    task_process = schedule_execution.task_processes[task_id]
                except KeyError:
                    continue

                # TODO: The schedule might disappear
                #       This problem is rampant in the code base for
                #       _schedules and _scheduled_processes
                schedule = self._schedules[schedule_id]

                self._logger.info(
                    "Terminating: Schedule '%s' process '%s' task %s pid %s\n%s",
                    schedule.name,
                    schedule.process_name,
                    task_id,
                    task_process.process.pid,
                    self._process_scripts[schedule.process_name])

                try:
                    task_process.process.terminate()
                except ProcessLookupError:
                    pass  # Process has terminated

        await asyncio.sleep(.1)  # sleep 0 doesn't give the process enough time to quit

        if self._active_task_count:
            raise TimeoutError()

        self._logger.info("Stopped")
        self._start_time = None

        return True

    async def _start_task(self, schedule: _ScheduleRow) -> Optional[uuid.UUID]:
        """Starts a task process

        Raises:
            IOError: If the process could not start

        """
        if self._paused:
            raise PausedError

        task_id = uuid.uuid4()
        args = self._process_scripts[schedule.process_name]
        self._logger.info("Starting: Schedule '%s' process '%s' task %s\n%s",
                          schedule.name, schedule.process_name, task_id, args)

        # The active task count is incremented prior to any
        # 'await' calls. Otherwise, a stop() request
        # would terminate before the process gets
        # started and tracked.
        self._active_task_count += 1

        try:
            process = await asyncio.create_subprocess_exec(*args)
        except IOError:
            self._active_task_count -= 1
            self._logger.exception(
                "Unable to start schedule '%s' process '%s' task %s\n%s".format(
                    schedule.name, schedule.process_name, task_id, args))
            raise

        task_process = self._TaskProcess()
        task_process.process = process

        self._schedule_executions[schedule.id].task_processes[task_id] = task_process

        self._logger.info(
            "Started: Schedule '%s' process '%s' task %s pid %s\n%s",
            schedule.name, schedule.process_name, task_id, process.pid, args)

        if schedule.type == self._ScheduleType.STARTUP:
            """Startup tasks are not tracked in the tasks table"""
            asyncio.ensure_future(self._wait_for_startup_task_completion(schedule, task_id))
        else:
            # The task row needs to exist before the completion handler runs
            async with aiopg.sa.create_engine(_CONNECTION_STRING) as engine:
                async with engine.acquire() as conn:
                    await conn.execute(self._tasks_tbl.insert().values(
                        id=str(task_id),
                        pid=(self._schedule_executions[schedule.id].
                             task_processes[task_id].process.pid),
                        process_name=schedule.process_name,
                        state=int(self._TaskState.RUNNING),
                        start_time=datetime.datetime.now()))

            asyncio.ensure_future(self._wait_for_task_completion(schedule, task_id))

        return task_id

    def _on_task_completion(self,
                            schedule: _ScheduleRow,
                            task_process: _TaskProcess,
                            task_id: uuid.UUID,
                            exit_code: int) -> None:
        """Called when a task process terminates.

        Determines the next start time for exclusive schedules.
        """
        self._logger.info(
            "Exited: Schedule '%s' process '%s' task %s pid %s exit %s\n%s",
            schedule.name,
            schedule.process_name,
            task_id,
            task_process.process.pid,
            exit_code,
            self._process_scripts[schedule.process_name])

        if self._active_task_count:
            self._active_task_count -= 1
        else:
            # This should not happen!
            self._logger.error("Active task count would be negative")

        schedule_execution = self._schedule_executions[schedule.id]

        if (schedule_execution.task_processes.len() == 1 and
                self._paused or (schedule.repeat is None and not schedule_execution.start_now)):
            if schedule_execution.next_start_time:
                # The above if statement avoids logging this message twice
                # for nonexclusive schedules
                self._logger.info(
                    "Tasks will no longer execute for schedule '%s'", schedule.name)
            del self._schedule_executions[schedule.id]
        else:
            del schedule_execution.task_processes[task_id]

            if schedule.exclusive and self._schedule_next_task(schedule):
                self._resume_check_schedules()

    async def _wait_for_startup_task_completion(self, schedule, task_id):
        task_process = self._schedule_executions[schedule.id].task_processes[task_id]

        exit_code = None
        try:
            exit_code = await task_process.process.wait()
        except Exception:  # TODO: catch real exception
            pass

        self._on_task_completion(schedule, task_process, task_id, exit_code)

    async def _wait_for_task_completion(self, schedule, task_id):
        task_process = self._schedule_executions[schedule.id].task_processes[task_id]

        exit_code = None
        try:
            exit_code = await task_process.process.wait()
        except Exception:  # TODO: catch real exception
            pass

        self._on_task_completion(schedule, task_process, task_id, exit_code)

        # Update the task's status
        # TODO if no row updated output a WARN row
        async with aiopg.sa.create_engine(_CONNECTION_STRING) as engine:
            async with engine.acquire() as conn:
                result = await conn.execute(
                    self._tasks_tbl.update().where(
                        self._tasks_tbl.c.id == str(task_id)).values(
                                exit_code=exit_code,
                                state=int(self._TaskState.COMPLETE),
                                end_time=datetime.datetime.now()))
                if result.rowcount == 0:
                    self._logger.warning("Task %s not found. Unable to update its status", task_id)

    async def start_task(self, schedule: Schedule)->None:
        """Starts a task for a schedule

        Args:
            schedule:
                Only the schedule_id needs to be set. It isn't necessary to
                use a specific child class.

        Raises:
            PausedError

            ScheduleNotFoundError

            TaskRunningError:
                The schedule is marked exclusive and a task
                is already running for the schedule

            TaskQueuedError:
                The task has already been queued for execution

        """
        if self._paused:
            raise PausedError()

        try:
            schedule_row = self._schedules[schedule.schedule_id]
        except KeyError:
            raise ScheduleNotFoundError(schedule.schedule_id)

        try:
            schedule_execution = self._schedule_executions[schedule_row.id]
        except KeyError:
            schedule_execution = None

        if schedule_execution and schedule_execution.start_now:
            raise TaskQueuedError()

        if schedule_execution and schedule_row.exclusive and schedule_execution.task_processes:
            raise TaskRunningError(
                    "Unable to start a task because the the schedule is marked exclusive"
                    "and a task is already running for the schedule.")

        if not schedule_execution:
            schedule_execution = self._ScheduleExecution()
            self._schedule_executions[schedule_row.id] = schedule_execution

        schedule_execution.start_now = True

        self._logger.info("Queued schedule '%s' for execution", schedule.name)
        self._resume_check_schedules()

    async def _check_schedules(self):
        """Starts tasks according to schedules based on the current time"""
        earliest_start_time = None

        # Can not iterate over _next_starts - it can change mid-iteration
        for key in list(self._schedule_executions.keys()):
            if self._paused:
                return None

            try:
                schedule_execution = self._schedule_executions[key]
            except KeyError:
                continue

            try:
                schedule = self._schedules[key]
            except KeyError:
                continue

            if schedule.exclusive and schedule_execution.task_processes:
                continue

            # next_start_time is None when repeat is None until the
            # task completes, at which time schedule_execution is removed
            next_start_time = schedule_execution.next_start_time

            right_time = time.time() >= next_start_time

            if right_time or schedule_execution.start_now:
                # Time to start a task

                # Queued manual execution is ignored if it was
                # already time to run the task. The task doesn't
                # start twice even when nonexclusive.
                schedule_execution.start_now = False

                if not right_time:
                    # Manual start - don't change next_start_time
                    pass
                elif not schedule.exclusive and self._schedule_next_task(schedule):
                    # _schedule_next_task alters next_start_time
                    next_start_time = schedule_execution.next_start_time
                else:
                    # Exclusive tasks won't start again until they terminate
                    # Or the schedule doesn't repeat
                    next_start_time = None

                try:
                    await self._start_task(schedule)
                except IOError:
                    # Avoid constantly running into the same error
                    if not schedule_execution.task_processes:
                        try:
                            del self._schedule_executions[schedule.id]
                        except KeyError:
                            pass
                except PausedError:
                    return None

            # Keep track of the earliest next_start_time
            if next_start_time is not None and (earliest_start_time is None
                                                or earliest_start_time > next_start_time):
                earliest_start_time = next_start_time

        return earliest_start_time

    def _schedule_next_timed_task(self, schedule, schedule_execution, current_dt):
        """Handle daylight savings time transitions.
           Assume 'repeat' is not null.

        """
        if schedule.repeat_seconds < self._DAY_SECONDS:
            # If repeat is less than a day, use the current hour.
            # Ignore the hour specified in the schedule's time.
            dt = datetime.datetime(
                year=current_dt.year,
                month=current_dt.month,
                day=current_dt.day,
                hour=current_dt.hour,
                minute=schedule.time.minute,
                second=schedule.time.second)

            if current_dt.time() > schedule.time:
                # It's already too late. Try for an hour later.
                dt += self._ONE_HOUR
        else:
            dt = datetime.datetime(
                year=current_dt.year,
                month=current_dt.month,
                day=current_dt.day,
                hour=schedule.time.hour,
                minute=schedule.time.minute,
                second=schedule.time.second)

            if current_dt.time() > schedule.time:
                # It's already too late. Try for tomorrow
                dt += self._ONE_DAY

        # Advance to the correct day if specified
        if schedule.day:
            while dt.isoweekday() != schedule.day:
                dt += self._ONE_DAY

        schedule_execution.next_start_time = time.mktime(dt.timetuple())

    def _schedule_first_task(self, schedule, current_time):
        """Determines the time when a task for a schedule will start.

        Args:
            schedule: The schedule to consider

            current_time:
                Epoch time to use as the current time when determining
                when to schedule tasks

        """
        try:
            schedule_execution = self._schedule_executions[schedule.id]
        except KeyError:
            schedule_execution = self._ScheduleExecution()
            self._schedule_executions[schedule.id] = schedule_execution

        if schedule.type == self._ScheduleType.INTERVAL:
            advance_seconds = schedule.repeat_seconds

            if advance_seconds:
                advance_seconds *= max([1, math.ceil(
                    (current_time - self._start_time) / advance_seconds)])

            schedule_execution.next_start_time = current_time + advance_seconds
        elif schedule.type == self._ScheduleType.TIMED:
            self._schedule_next_timed_task(
                schedule,
                schedule_execution,
                datetime.datetime.fromtimestamp(current_time))
        elif schedule.type == self._ScheduleType.STARTUP:
            schedule_execution.next_start_time = current_time

        self._logger.info(
            "Scheduled '%s' for %s", schedule.name,
            datetime.datetime.fromtimestamp(schedule_execution.next_start_time))

    def _schedule_next_task(self, schedule):
        """Computes the next time to start a task for a schedule.

        This method is called only for schedules that have repeat != None.

        For nonexclusive schedules, this method is called after starting
        a task automatically (it is not called when a task is started
        manually).

        For exclusive schedules, this method is called after the task
        has completed.

        """
        schedule_execution = self._schedule_executions[schedule.id]
        advance_seconds = schedule.repeat_seconds

        if self._paused or advance_seconds is None:
            schedule_execution.next_start_time = None
            self._logger.info(
                "Tasks will no longer execute for schedule '%s'", schedule.name)
            return False

        now = time.time()

        if schedule.exclusive and now < schedule_execution.next_start_time:
            # The task was started manually
            return False

        if advance_seconds:
            advance_seconds *= max([1, math.ceil(
                (now - schedule_execution.next_start_time) / advance_seconds)])

            if schedule.type == self._ScheduleType.TIMED:
                # Handle daylight savings time transitions
                next_dt = datetime.datetime.fromtimestamp(schedule_execution.next_start_time)
                next_dt += datetime.timedelta(seconds=advance_seconds)

                if schedule.day is not None and next_dt.isoweekday() != schedule.day:
                    # Advance to the next matching day
                    next_dt = datetime.datetime(year=next_dt.year,
                                                month=next_dt.month,
                                                day=next_dt.day)
                    self._schedule_next_timed_task(schedule, schedule_execution, next_dt)
                else:
                    schedule_execution.next_start_time = time.mktime(next_dt.timetuple())
            else:
                # Interval schedule
                schedule_execution.next_start_time += advance_seconds

            self._logger.info(
                "Scheduled '%s' for %s", schedule.name,
                datetime.datetime.fromtimestamp(schedule_execution.next_start_time))

        return True

    async def _get_process_scripts(self):
        query = sa.select([self._scheduled_processes_tbl.c.name,
                           self._scheduled_processes_tbl.c.script])
        query.select_from(self._scheduled_processes_tbl)

        async with aiopg.sa.create_engine(_CONNECTION_STRING) as engine:
            async with engine.acquire() as conn:
                async for row in conn.execute(query):
                    self._process_scripts[row.name] = row.script

    async def _mark_tasks_interrupted(self):
        """Any task with a NULL end_time is set to interrupted"""
        async with aiopg.sa.create_engine(_CONNECTION_STRING) as engine:
            async with engine.acquire() as conn:
                await conn.execute(
                    self._tasks_tbl.update().where(
                        self._tasks_tbl.c.end_time is None).values(
                            state=int(self._TaskState.INTERRUPTED),
                            end_time=datetime.datetime.now()))

    async def _get_schedules(self):
        # TODO: Get processes first, then add to Schedule
        query = sa.select([self._schedules_tbl.c.id,
                           self._schedules_tbl.c.schedule_name,
                           self._schedules_tbl.c.schedule_type,
                           self._schedules_tbl.c.schedule_time,
                           self._schedules_tbl.c.schedule_day,
                           self._schedules_tbl.c.schedule_interval,
                           self._schedules_tbl.c.exclusive,
                           self._schedules_tbl.c.process_name])

        query.select_from(self._schedules_tbl)

        async with aiopg.sa.create_engine(_CONNECTION_STRING) as engine:
            async with engine.acquire() as conn:
                async for row in conn.execute(query):
                    interval = row.schedule_interval

                    repeat_seconds = None
                    if interval is not None:
                        repeat_seconds = interval.total_seconds()

                    schedule = self._ScheduleRow(
                                        id=row.id,
                                        name=row.schedule_name,
                                        type=row.schedule_type,
                                        day=row.schedule_day,
                                        time=row.schedule_time,
                                        repeat=interval,
                                        repeat_seconds=repeat_seconds,
                                        exclusive=row.exclusive,
                                        process_name=row.process_name)

                    # TODO: Move this to _add_schedule to check for errors
                    self._schedules[row.id] = schedule
                    self._schedule_first_task(schedule, self._start_time)

    async def _read_storage(self):
        """Reads schedule information from the storage server"""
        await self._get_process_scripts()
        await self._get_schedules()

    def _resume_check_schedules(self):
        if self._main_sleep_task:
            self._main_sleep_task.cancel()

    async def _main_loop(self):
        """Main loop for the scheduler

        - Reads configuration and schedules
        - Runs :meth:`Scheduler._check_schedules` in an endless loop
        """
        # TODO: log exception here or add an exception handler in asyncio

        while True:
            next_start_time = await self._check_schedules()

            if self._paused:
                break

            if next_start_time is None:
                sleep_seconds = self._MAX_SLEEP
            else:
                sleep_seconds = next_start_time - time.time()

            if sleep_seconds > 0:
                self._logger.info("Sleeping for %s seconds", sleep_seconds)
                self._main_sleep_task = asyncio.ensure_future(asyncio.sleep(sleep_seconds))

                try:
                    await self._main_sleep_task
                except asyncio.CancelledError:
                    self._logger.debug("Main loop awakened")
                    pass

                self._main_sleep_task = None

    @staticmethod
    async def reset_for_testing():
        """Delete all schedule-related tables and insert processes for testing"""
        async with aiopg.sa.create_engine(_CONNECTION_STRING) as engine:
            async with engine.acquire() as conn:
                await conn.execute('delete from foglamp.tasks')
                await conn.execute('delete from foglamp.schedules')
                await conn.execute('delete from foglamp.scheduled_processes')
                await conn.execute(
                    '''insert into foglamp.scheduled_processes(name, script)
                    values('sleep1', '["sleep", "1"]')''')
                await conn.execute(
                    '''insert into foglamp.scheduled_processes(name, script)
                    values('sleep10', '["sleep", "10"]')''')

    async def save_schedule(self, schedule: Schedule):
        """Creates or update a schedule

        Args:
            schedule:
                The id can be None, in which case a new id will be generated
        """
        schedule_type = None
        day = None
        schedule_time = None

        # TODO: verify schedule object (day, etc)

        if isinstance(schedule, IntervalSchedule):
            schedule_type = self._ScheduleType.INTERVAL
        elif isinstance(schedule, StartUpSchedule):
            schedule_type = self._ScheduleType.STARTUP
        elif isinstance(schedule, TimedSchedule):
            schedule_type = self._ScheduleType.TIMED
            schedule_time = schedule.time
            day = schedule.day
        elif isinstance(schedule, ManualSchedule):
            schedule_type = self._ScheduleType.MANUAL

        is_new_schedule = False

        if schedule.schedule_id is None:
            is_new_schedule = True
            schedule.schedule_id = uuid.uuid4()

        schedule_id = str(schedule.schedule_id)

        if not is_new_schedule:
            async with aiopg.sa.create_engine(_CONNECTION_STRING) as engine:
                async with engine.acquire() as conn:
                    result = await conn.execute(
                        self._schedules_tbl.update().where(
                            self._schedules_tbl.c.id == schedule_id).values(
                            schedule_name=schedule.name,
                            schedule_interval=schedule.repeat,
                            schedule_day=day,
                            schedule_time=schedule_time,
                            exclusive=schedule.exclusive,
                            process_name=schedule.process_name
                        ))

                    if result.rowcount == 0:
                        is_new_schedule = True

        if is_new_schedule:
            async with aiopg.sa.create_engine(_CONNECTION_STRING) as engine:
                async with engine.acquire() as conn:
                    await conn.execute(self._schedules_tbl.insert().values(
                        id=schedule_id,
                        schedule_type=int(schedule_type),
                        schedule_name=schedule.name,
                        schedule_interval=schedule.repeat,
                        schedule_day=day,
                        schedule_time=schedule_time,
                        exclusive=schedule.exclusive,
                        process_name=schedule.process_name))

        # TODO: Move this to _add_schedule
        repeat_seconds = None
        if schedule.repeat is not None:
            repeat_seconds = schedule.repeat.total_seconds()

        schedule_row = self._ScheduleRow(
                                id=schedule.schedule_id,
                                name=schedule.name,
                                type=schedule_type,
                                time=schedule_time,
                                day=day,
                                repeat=schedule.repeat,
                                repeat_seconds=repeat_seconds,
                                exclusive=schedule.exclusive,
                                process_name=schedule.process_name)

        if is_new_schedule:
            prev_schedule_row = None
        else:
            prev_schedule_row = self._schedules[schedule.schedule_id]

        self._schedules[schedule.schedule_id] = schedule_row

        # Did the schedule change in a way that will affect task scheduling?

        if schedule_type in [self._ScheduleType.INTERVAL,
                             self._ScheduleType.TIMED] and (
                is_new_schedule or
                prev_schedule_row.time != schedule_row.time or
                prev_schedule_row.day != schedule_row.day or
                prev_schedule_row.repeat_seconds != schedule_row.repeat_seconds or
                prev_schedule_row.exclusive != schedule_row.exclusive):
            self._schedule_first_task(schedule_row, time.time())
            self._resume_check_schedules()

    async def start(self):
        """Starts the scheduler

        When this method returns, an asyncio task is
        scheduled that starts tasks and monitors subprocesses. This class
        does not use threads (tasks run as subprocesses).

        Raises RuntimeError:
            Scheduler already started
        """
        if self._start_time:
            raise RuntimeError("The scheduler is already running")

        self._start_time = time.time()
        self._logger.info("Starting")

        # Hard-code storage server:
        # wait self._start_startup_task(self._schedules['storage'])
        # Then wait for it to start.

        await self._mark_tasks_interrupted()
        await self._read_storage()

        asyncio.ensure_future(self._main_loop())
