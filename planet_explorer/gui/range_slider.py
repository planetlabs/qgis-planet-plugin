# -*- coding: utf-8 -*-

"""
***************************************************************************
    range_slider.py
    ---------------------
    Date                 : August 2019
    Copyright            : (C) 2019 Planet Inc, https://www.planet.com
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************


Based upon work by Enthought...
***************************************************************************
https://github.com/enthought/traitsui/blob/
24e0f71dca8ff7c28080b247bc48827ee13dcd02/traitsui/qt4/extra/range_slider.py

This software is OSI Certified Open Source Software.
OSI Certified is a certification mark of the Open Source Initiative.

Copyright (c) 2006-2018, Enthought, Inc.
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

 * Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.
 * Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.
 * Neither the name of Enthought, Inc. nor the names of its contributors may
   be used to endorse or promote products derived from this software without
   specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

The software contained in the traits/protocols/ directory is
the pyprotocols project (http://peak.telecommunity.com/PyProtocols.html),
it is originaly licensed under the terms of the Python Software
Foundation License, which is compatible with the above terms.
***************************************************************************
"""

__author__ = 'Planet Federal'
__date__ = 'August 2019'
__copyright__ = '(C) 2019 Planet Inc, https://www.planet.com'

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = '$Format:%H$'


from qgis.PyQt.QtCore import Qt, pyqtSignal, pyqtSlot, QRectF
from qgis.PyQt.QtGui import QPainter, QBrush, QColor
from qgis.PyQt.QtWidgets import (
    QSlider, QStyle, QStyleOptionSlider, QStyleFactory
)


# noinspection PyPep8Naming,PyUnresolvedReferences
class RangeSlider(QSlider):
    """ A slider for ranges.

        This class provides a dual-slider for ranges, where there is a defined
        maximum and minimum, as is a normal slider, but instead of having a
        single slider value, there are 2 slider values.

        This class emits the same signals as the QSlider base class, with the
        exception of valueChanged
    """

    activeRangeChanged = pyqtSignal(int, int)
    finalRangeChanged = pyqtSignal(int, int)

    def __init__(self, *args, **kwargs):
        super(RangeSlider, self).__init__(*args, **kwargs)

        self._low = self.minimum()
        self._high = self.maximum()

        self._cur_low = self._low
        self._cur_high = self._high

        self.pressed_control = QStyle.SC_None
        self.hover_control = QStyle.SC_None
        self.click_offset = 0

        # 0 for the low, 1 for the high, -1 for both
        self.active_slider = 0

        # self.sliderMoved[int].connect(self.value_changed)

        # self.setStyleSheet("""
        # QSlider::groove:vertical {
        #         background-color: #222;
        #         width: 30px;
        # }
        # QSlider::handle:vertical {
        #     border: 1px #438f99;
        #     border-style: outset;
        #     margin: -2px 0;
        #     width: 30px;
        #     height: 3px;
        #     background-color: #438f99;
        # }
        # QSlider::sub-page:vertical {
        #     background: #4B4B4B;
        # }
        # QSlider::groove:horizontal {
        #         background-color: #222;
        #         height: 30px;
        # }
        # QSlider::handle:horizontal {
        #     border: 1px #438f99;
        #     border-style: outset;
        #     margin: -2px 0;
        #     width: 3px;
        #     height: 30px;
        #     background-color: #438f99;
        # }
        # QSlider::sub-page:horizontal {
        #     background: #4B4B4B;
        # }
        # """)

        # self.setStyleSheet("""
        # RangeSlider::sub-page {
        #     background-color: rgba(0, 0, 0, 0%);
        # }
        # RangeSlider::add-page {
        #     background-color: rgba(0, 0, 0, 0%);
        # }
        # """)

        # self.setStyleSheet('''
        # QSlider::sub-page:horizontal {background-color: #222;height: 4px;}
        # ''')

    # @pyqtSlot(int)
    # def value_changed(self, val):
    #     # print(val)
    #     if self.isSliderDown():
    #         return
    #
    #     if (self._cur_low, self._cur_high) != (self._low, self._high):
    #         self._cur_low, self._cur_high = self._low, self._high
    #         self.activeRangeChanged[int, int].emit(self._low, self._high)

    def low(self):
        return self._low

    def setLow(self, low):
        self._low = low
        self._cur_low = low
        self.update()

    def high(self):
        return self._high

    def setHigh(self, high):
        self._high = high
        self._cur_high = high
        self.update()

    def paintEvent(self, event):
        # based on
        # http://qt.gitorious.org/qt/qt/blobs/master/src/gui/widgets/qslider.cpp

        painter = QPainter(self)
        style = self.style()
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)

        groove_rect = style.subControlRect(
            style.CC_Slider, opt, QStyle.SC_SliderGroove, self)
        handle_rect = style.subControlRect(
            style.CC_Slider, opt, QStyle.SC_SliderHandle, self)

        slider_space = style.pixelMetric(style.PM_SliderSpaceAvailable, opt)
        range_x1 = style.sliderPositionFromValue(
            self.minimum(), self.maximum(), self._low, slider_space)
        range_x2 = style.sliderPositionFromValue(
            self.minimum(), self.maximum(), self._high, slider_space)
        range_height = 4

        groove_rect = QRectF(
            groove_rect.x(),
            handle_rect.center().y() - (range_height / 2),
            groove_rect.width(),
            range_height)

        range_rect = QRectF(
            groove_rect.x() + (handle_rect.width() / 2) + range_x1,
            handle_rect.center().y() - (range_height / 2),
            range_x2 - range_x1,
            range_height)

        if style.metaObject().className() != 'QMacStyle':
            # Paint groove for Fusion and Windows styles
            cur_brush = painter.brush()
            cur_pen = painter.pen()
            painter.setBrush(QBrush(QColor(169, 169, 169)))
            painter.setPen(Qt.NoPen)
            # painter.drawRect(groove_rect)
            painter.drawRoundedRect(groove_rect,
                                    groove_rect.height() / 2,
                                    groove_rect.height() / 2)
            painter.setBrush(cur_brush)
            painter.setPen(cur_pen)

        cur_brush = painter.brush()
        cur_pen = painter.pen()
        painter.setBrush(QBrush(QColor(18, 141, 148)))
        painter.setPen(Qt.NoPen)
        painter.drawRect(range_rect)
        painter.setBrush(cur_brush)
        painter.setPen(cur_pen)

        for i, value in enumerate([self._low, self._high]):
            opt = QStyleOptionSlider()
            self.initStyleOption(opt)

            # Only draw the groove for the first slider so it doesn't get drawn
            # on top of the existing ones every time
            # if i == 0:
            #     opt.subControls = QStyle.SC_SliderGroove | \
            #                       QStyle.SC_SliderHandle
            # else:
            opt.subControls = QStyle.SC_SliderHandle

            if self.tickPosition() != self.NoTicks:
                opt.subControls |= QStyle.SC_SliderTickmarks

            if self.isSliderDown():
                opt.state |= QStyle.State_Sunken
            else:
                opt.state |= QStyle.State_Active

            if self.pressed_control:
                opt.activeSubControls = self.pressed_control
            else:
                opt.activeSubControls = self.hover_control

            opt.sliderPosition = value
            opt.sliderValue = value
            style.drawComplexControl(
                QStyle.CC_Slider, opt, painter, self)

    def mousePressEvent(self, event):
        event.accept()

        style = self.style()
        button = event.button()

        # In a normal slider control, when the user clicks on a point in the
        # slider's total range, but not on the slider part of the control the
        # control would jump the slider value to where the user clicked.
        # For this control, clicks which are not direct hits will slide both
        # slider parts

        if button:
            opt = QStyleOptionSlider()
            self.initStyleOption(opt)

            self.active_slider = -1

            self.setSliderDown(True)

            for i, value in enumerate([self._low, self._high]):
                opt.sliderPosition = value
                hit = style.hitTestComplexControl(
                    style.CC_Slider, opt, event.pos(), self)
                if hit == style.SC_SliderHandle:
                    self.active_slider = i
                    self.pressed_control = hit

                    self.triggerAction(self.SliderMove)
                    self.setRepeatAction(self.SliderNoAction)
                    # self.setSliderDown(True)
                    break

            if self.active_slider < 0:
                self.pressed_control = QStyle.SC_SliderHandle
                self.click_offset = self.__pixelPosToRangeValue(
                    self.__pick(event.pos()))
                self.triggerAction(self.SliderMove)
                self.setRepeatAction(self.SliderNoAction)

            self.update()
        else:
            event.ignore()

    def mouseMoveEvent(self, event):
        if self.pressed_control != QStyle.SC_SliderHandle:
            event.ignore()
            return

        event.accept()
        new_pos = self.__pixelPosToRangeValue(self.__pick(event.pos()))
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)

        if self.active_slider < 0:
            offset = new_pos - self.click_offset
            self._high += offset
            self._low += offset
            if self._low < self.minimum():
                diff = self.minimum() - self._low
                self._low += diff
                self._high += diff
            if self._high > self.maximum():
                diff = self.maximum() - self._high
                self._low += diff
                self._high += diff
        elif self.active_slider == 0:
            if new_pos >= self._high:
                new_pos = self._high - 1
            self._low = new_pos
        else:
            if new_pos <= self._low:
                new_pos = self._low + 1
            self._high = new_pos

        self.click_offset = new_pos

        self.update()

        self.sliderMoved.emit(new_pos)
        self.activeRangeChanged.emit(self._low, self._high)

    def mouseReleaseEvent(self, event):
        if (self.pressed_control == QStyle.SC_None
                or event.buttons()):
            event.ignore()
            return

        event.accept()

        old_pressed = QStyle.SubControl(self.pressed_control)
        self.pressed_control = QStyle.SC_None
        self.setRepeatAction(self.SliderNoAction)
        if old_pressed == QStyle.SC_SliderHandle:
            self.setSliderDown(False)
        # opt = QStyleOptionSlider()
        # self.initStyleOption(opt)
        # opt.subControls = old_pressed
        # style = self.style()
        # self.update(style.subControlRect(style.CC_Slider,
        #                                  opt, old_pressed, self))
        self.update()

        if (self._cur_low, self._cur_high) != (self._low, self._high):
            self._cur_low, self._cur_high = self._low, self._high
            self.finalRangeChanged[int, int].emit(self._low, self._high)

    def __pick(self, pt):
        if self.orientation() == Qt.Horizontal:
            return pt.x()
        else:
            return pt.y()

    def __pixelPosToRangeValue(self, pos):
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        style = self.style()

        gr = style.subControlRect(
            style.CC_Slider, opt, style.SC_SliderGroove, self)
        sr = style.subControlRect(
            style.CC_Slider, opt, style.SC_SliderHandle, self)

        if self.orientation() == Qt.Horizontal:
            slider_length = sr.width()
            slider_min = gr.x()
            slider_max = gr.right() - slider_length + 1
        else:
            slider_length = sr.height()
            slider_min = gr.y()
            slider_max = gr.bottom() - slider_length + 1

        return style.sliderValueFromPosition(
            self.minimum(),
            self.maximum(),
            pos - slider_min,
            slider_max - slider_min,
            opt.upsideDown)


if __name__ == "__main__":
    import sys
    from qgis.PyQt.QtWidgets import QApplication, QDialog, QVBoxLayout

    # @pyqtSlot(int)
    # def echo(value):
    #     print(value)

    @pyqtSlot(int, int)
    def echo_active_range(low, high):
        print(f'active... low: {low}, high: {high}')

    @pyqtSlot(int, int)
    def echo_final_range(low, high):
        print(f'final... low: {low}, high: {high}')

    app = QApplication(sys.argv)

    app.setStyle(QStyleFactory.create("Macintosh"))
    # app.setStyle(QStyleFactory.create("Fusion"))
    # app.setStyle(QStyleFactory.create("Windows"))
    print(f'app styles: {QStyleFactory.keys()}')
    print(f'app style: {app.style().metaObject().className()}')

    # wrap in dialog
    dlg = QDialog()
    dlg.setWindowTitle('RangeSlider test')
    layout = QVBoxLayout(dlg)

    slider = RangeSlider(Qt.Horizontal, parent=dlg)
    slider.setMinimum(0)
    slider.setMaximum(100)
    slider.setLow(25)
    slider.setHigh(75)
    slider.setTickPosition(slider.TicksBelow)
    slider.setTickInterval(int((slider.maximum() - slider.minimum()) / 2))

    # slider.sliderMoved.connect(echo)
    # noinspection PyUnresolvedReferences
    slider.activeRangeChanged.connect(echo_active_range)
    # noinspection PyUnresolvedReferences
    slider.finalRangeChanged.connect(echo_final_range)

    layout.addWidget(slider)
    # layout.setMargin(0)

    dlg.show()
    app.exec_()
