from __future__ import annotations


_WINDOWS_UIA_LIST_ELEMENTS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$payloadText = [Console]::In.ReadToEnd()
$payload = $payloadText | ConvertFrom-Json
Add-Type -AssemblyName UIAutomationClient
$hwnd = [IntPtr]([Int64]$payload.window_id)
$root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
if ($null -eq $root) { throw "UIAutomation root not found: $($payload.window_id)" }
$maxDepth = [int]$payload.max_depth
$maxElements = [int]$payload.max_elements
$walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
$queue = New-Object 'System.Collections.Generic.Queue[object]'
$queue.Enqueue([pscustomobject]@{ Element = $root; Depth = 0; Parent = '' })
$result = New-Object System.Collections.ArrayList
while ($queue.Count -gt 0 -and $result.Count -lt $maxElements) {
  $item = $queue.Dequeue()
  $element = $item.Element
  try {
    $current = $element.Current
    $rect = $current.BoundingRectangle
    $runtimeId = ''
    try { $runtimeId = ($element.GetRuntimeId() -join '.') } catch {}
    $value = ''
    try {
      $patternObj = $null
      if ($element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$patternObj)) {
        $value = [string]$patternObj.Current.Value
      }
    } catch {}
    $controlType = ''
    try {
      $controlType = [string]$current.ControlType.ProgrammaticName
      $controlType = $controlType -replace '^ControlType\.', ''
    } catch {}
    $obj = [ordered]@{
      id = $runtimeId
      runtime_id = $runtimeId
      name = [string]$current.Name
      value = $value
      text = $(if ($value) { $value } else { [string]$current.Name })
      automation_id = [string]$current.AutomationId
      control_type = $controlType
      localized_control_type = [string]$current.LocalizedControlType
      role = $controlType
      class_name = [string]$current.ClassName
      enabled = [bool]$current.IsEnabled
      visible = -not [bool]$current.IsOffscreen
      focused = [bool]$current.HasKeyboardFocus
      bounds = @{
        x = [int][Math]::Round($rect.X)
        y = [int][Math]::Round($rect.Y)
        width = [int][Math]::Round($rect.Width)
        height = [int][Math]::Round($rect.Height)
      }
      depth = [int]$item.Depth
      parent_id = [string]$item.Parent
    }
    [void]$result.Add($obj)
    if ($item.Depth -lt $maxDepth) {
      $child = $walker.GetFirstChild($element)
      while ($null -ne $child) {
        $queue.Enqueue([pscustomobject]@{ Element = $child; Depth = ([int]$item.Depth + 1); Parent = $runtimeId })
        $child = $walker.GetNextSibling($child)
      }
    }
  } catch {}
}
[ordered]@{
  ok = $true
  elements = $result
  count = $result.Count
  truncated = ($queue.Count -gt 0)
} | ConvertTo-Json -Depth 8 -Compress
"""


_WINDOWS_UIA_ACTION_ELEMENT_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$payloadText = [Console]::In.ReadToEnd()
$payload = $payloadText | ConvertFrom-Json
Add-Type -AssemblyName UIAutomationClient
$hwnd = [IntPtr]([Int64]$payload.window_id)
$root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
if ($null -eq $root) { throw "UIAutomation root not found: $($payload.window_id)" }
$maxDepth = [int]$payload.max_depth
$maxElements = [int]$payload.max_elements
$locator = $payload.locator
if ($null -eq $locator) { $locator = [pscustomobject]@{} }
$operation = [string]$payload.operation
$value = [string]$payload.value
$runtimeId = [string]$payload.runtime_id
$optionIndex = $null
if ($null -ne $payload.option_index) {
  try { $optionIndex = [int]$payload.option_index } catch { $optionIndex = $null }
}
$matchIndex = 0
try { $matchIndex = [int]$locator.element_match_index } catch {}

function Get-PropText($obj, [string]$name) {
  $prop = $obj.PSObject.Properties[$name]
  if ($null -eq $prop -or $null -eq $prop.Value) { return '' }
  return [string]$prop.Value
}

function Test-RegexValue([string]$pattern, [string]$value) {
  if ([string]::IsNullOrEmpty($pattern)) { return $true }
  try { return [regex]::IsMatch($value, $pattern) } catch { return $false }
}

function Test-TypeMatch($obj, [string]$expected) {
  if ([string]::IsNullOrEmpty($expected)) { return $true }
  $expectedLower = $expected.ToLowerInvariant()
  foreach ($field in @('control_type', 'localized_control_type', 'role')) {
    $candidate = (Get-PropText $obj $field).ToLowerInvariant()
    if ($candidate -eq $expectedLower -or $candidate.Contains($expectedLower)) { return $true }
  }
  return $false
}

function Get-UiaRuntimeId([System.Windows.Automation.AutomationElement]$element) {
  try { return ($element.GetRuntimeId() -join '.') } catch { return '' }
}

function Get-UiaValue([System.Windows.Automation.AutomationElement]$element) {
  try {
    $patternObj = $null
    if ($element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$patternObj)) {
      return [string]$patternObj.Current.Value
    }
  } catch {}
  return ''
}

function Convert-UiaElement(
  [System.Windows.Automation.AutomationElement]$element,
  [int]$depth,
  [string]$parentId
) {
  $current = $element.Current
  $rect = $current.BoundingRectangle
  $runtime = Get-UiaRuntimeId $element
  $uiaValue = Get-UiaValue $element
  $controlType = ''
  try {
    $controlType = [string]$current.ControlType.ProgrammaticName
    $controlType = $controlType -replace '^ControlType\.', ''
  } catch {}
  return [ordered]@{
    id = $runtime
    runtime_id = $runtime
    name = [string]$current.Name
    value = $uiaValue
    text = $(if ($uiaValue) { $uiaValue } else { [string]$current.Name })
    automation_id = [string]$current.AutomationId
    control_type = $controlType
    localized_control_type = [string]$current.LocalizedControlType
    role = $controlType
    class_name = [string]$current.ClassName
    enabled = [bool]$current.IsEnabled
    visible = -not [bool]$current.IsOffscreen
    focused = [bool]$current.HasKeyboardFocus
    bounds = @{
      x = [int][Math]::Round($rect.X)
      y = [int][Math]::Round($rect.Y)
      width = [int][Math]::Round($rect.Width)
      height = [int][Math]::Round($rect.Height)
    }
    depth = $depth
    parent_id = $parentId
  }
}

function Test-LocatorMatch($obj, $locator) {
  $names = $locator.PSObject.Properties.Name
  if ($names -contains 'element_id' -and (Get-PropText $obj 'id') -ne [string]$locator.element_id) { return $false }
  if ($names -contains 'automation_id' -and (Get-PropText $obj 'automation_id') -ne [string]$locator.automation_id) { return $false }
  if ($names -contains 'name' -and (Get-PropText $obj 'name') -ne [string]$locator.name) { return $false }
  if ($names -contains 'name_contains' -and -not (Get-PropText $obj 'name').Contains([string]$locator.name_contains)) { return $false }
  if ($names -contains 'name_regex' -and -not (Test-RegexValue ([string]$locator.name_regex) (Get-PropText $obj 'name'))) { return $false }
  $elementText = Get-PropText $obj 'text'
  if ($names -contains 'text' -and $elementText -ne [string]$locator.text) { return $false }
  if ($names -contains 'text_contains' -and -not $elementText.Contains([string]$locator.text_contains)) { return $false }
  if ($names -contains 'text_regex' -and -not (Test-RegexValue ([string]$locator.text_regex) $elementText)) { return $false }
  if ($names -contains 'control_type' -and -not (Test-TypeMatch $obj ([string]$locator.control_type))) { return $false }
  if ($names -contains 'role' -and -not (Test-TypeMatch $obj ([string]$locator.role))) { return $false }
  if ($names -contains 'element_class_name') {
    $expected = ([string]$locator.element_class_name).ToLowerInvariant()
    $actual = (Get-PropText $obj 'class_name').ToLowerInvariant()
    if (-not $actual.Contains($expected)) { return $false }
  }
  return $true
}

function Test-OptionMatch($obj, [string]$optionValue, $optionIndex, [int]$matchOrder) {
  if ($null -ne $optionIndex -and $matchOrder -eq [int]$optionIndex) { return $true }
  if ([string]::IsNullOrEmpty($optionValue)) { return $false }
  $name = Get-PropText $obj 'name'
  $text = Get-PropText $obj 'text'
  $valueText = Get-PropText $obj 'value'
  return $name -eq $optionValue -or $text -eq $optionValue -or $valueText -eq $optionValue
}

function Find-OptionElement(
  [System.Windows.Automation.AutomationElement]$rootElement,
  [string]$optionValue,
  $optionIndex,
  [int]$maxDepth,
  [int]$maxElements
) {
  $optionControlTypes = @(
    [System.Windows.Automation.ControlType]::ListItem,
    [System.Windows.Automation.ControlType]::DataItem,
    [System.Windows.Automation.ControlType]::MenuItem,
    [System.Windows.Automation.ControlType]::TreeItem
  )
  $optionWalker = [System.Windows.Automation.TreeWalker]::RawViewWalker
  $queue = New-Object 'System.Collections.Generic.Queue[object]'
  $queue.Enqueue([pscustomobject]@{ Element = $rootElement; Depth = 0; Parent = '' })
  $visited = 0
  $candidateIndex = 0
  while ($queue.Count -gt 0 -and $visited -lt $maxElements) {
    $item = $queue.Dequeue()
    $element = $item.Element
    try {
      $obj = Convert-UiaElement $element ([int]$item.Depth) ([string]$item.Parent)
      $visited += 1
      $controlType = $element.Current.ControlType
      $isOptionType = $optionControlTypes -contains $controlType
      if ($isOptionType -and (Test-OptionMatch $obj $optionValue $optionIndex $candidateIndex)) {
        return [pscustomobject]@{ Element = $element; Payload = $obj }
      }
      if ($isOptionType) { $candidateIndex += 1 }
      if ($item.Depth -lt $maxDepth) {
        $child = $optionWalker.GetFirstChild($element)
        while ($null -ne $child) {
          $queue.Enqueue([pscustomobject]@{ Element = $child; Depth = ([int]$item.Depth + 1); Parent = [string]$obj.runtime_id })
          $child = $optionWalker.GetNextSibling($child)
        }
      }
    } catch {}
  }
  return $null
}

$walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
$queue = New-Object 'System.Collections.Generic.Queue[object]'
$queue.Enqueue([pscustomobject]@{ Element = $root; Depth = 0; Parent = '' })
$selectedElement = $null
$selectedPayload = $null
$matched = 0
$visited = 0
while ($queue.Count -gt 0 -and $visited -lt $maxElements) {
  $item = $queue.Dequeue()
  $element = $item.Element
  try {
    $obj = Convert-UiaElement $element ([int]$item.Depth) ([string]$item.Parent)
    $visited += 1
    $isRuntimeMatch = -not [string]::IsNullOrEmpty($runtimeId) -and [string]$obj.runtime_id -eq $runtimeId
    if ($isRuntimeMatch -or (Test-LocatorMatch $obj $locator)) {
      if ($isRuntimeMatch -or $matched -eq $matchIndex) {
        $selectedElement = $element
        $selectedPayload = $obj
        break
      }
      $matched += 1
    }
    if ($item.Depth -lt $maxDepth) {
      $child = $walker.GetFirstChild($element)
      while ($null -ne $child) {
        $queue.Enqueue([pscustomobject]@{ Element = $child; Depth = ([int]$item.Depth + 1); Parent = [string]$obj.runtime_id })
        $child = $walker.GetNextSibling($child)
      }
    }
  } catch {}
}
if ($null -eq $selectedElement) { throw "UIAutomation element not found: locator=$($locator | ConvertTo-Json -Compress)" }

$method = ''
$fallbackRequired = $false
$fallbackError = ''
if ($operation -eq 'invoke') {
  try {
    $patternObj = $null
    if ($selectedElement.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$patternObj)) {
      $patternObj.Invoke()
      $method = 'uia_invoke_pattern'
    } else {
      $fallbackRequired = $true
      $method = 'bounds_click_fallback'
      $fallbackError = 'InvokePattern unavailable'
    }
  } catch {
    $fallbackRequired = $true
    $method = 'bounds_click_fallback'
    $fallbackError = $_.Exception.Message
  }
} elseif ($operation -eq 'set_text') {
  try {
    $patternObj = $null
    if ($selectedElement.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$patternObj)) {
      if ([bool]$patternObj.Current.IsReadOnly) {
        $fallbackRequired = $true
        $method = 'keyboard_clipboard_fallback'
        $fallbackError = 'ValuePattern is read-only'
      } else {
        $patternObj.SetValue($value)
        $method = 'uia_value_pattern'
      }
    } else {
      $fallbackRequired = $true
      $method = 'keyboard_clipboard_fallback'
      $fallbackError = 'ValuePattern unavailable'
    }
  } catch {
    $fallbackRequired = $true
    $method = 'keyboard_clipboard_fallback'
    $fallbackError = $_.Exception.Message
  }
} elseif ($operation -eq 'select') {
  try {
    $patternObj = $null
    if ($selectedElement.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$patternObj) -and [string]::IsNullOrEmpty($value) -and $null -eq $optionIndex) {
      $patternObj.Select()
      $method = 'uia_selection_item_pattern'
    } else {
      $expandObj = $null
      try {
        if ($selectedElement.TryGetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern, [ref]$expandObj)) {
          if ($expandObj.Current.ExpandCollapseState -ne [System.Windows.Automation.ExpandCollapseState]::Expanded) {
            $expandObj.Expand()
            Start-Sleep -Milliseconds 150
          }
        }
      } catch {}
      $optionMatch = Find-OptionElement $selectedElement $value $optionIndex ([Math]::Min($maxDepth, 4)) $maxElements
      if ($null -eq $optionMatch) {
        $optionMatch = Find-OptionElement $root $value $optionIndex ([Math]::Min($maxDepth, 6)) $maxElements
      }
      if ($null -eq $optionMatch) {
        $fallbackRequired = $true
        $method = 'bounds_click_fallback'
        $fallbackError = 'Selection option not found'
      } else {
        $selectedPayload = $optionMatch.Payload
        $optionPatternObj = $null
        if ($optionMatch.Element.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$optionPatternObj)) {
          $optionPatternObj.Select()
          $method = 'uia_selection_item_pattern'
        } else {
          $invokeObj = $null
          if ($optionMatch.Element.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$invokeObj)) {
            $invokeObj.Invoke()
            $method = 'uia_invoke_option_pattern'
          } else {
            $fallbackRequired = $true
            $method = 'bounds_click_fallback'
            $fallbackError = 'SelectionItemPattern unavailable'
          }
        }
      }
    }
  } catch {
    $fallbackRequired = $true
    $method = 'bounds_click_fallback'
    $fallbackError = $_.Exception.Message
  }
} else {
  throw "Unsupported UIAutomation operation: $operation"
}

[ordered]@{
  ok = $true
  operation = $operation
  method = $method
  fallback_required = $fallbackRequired
  fallback_error = $fallbackError
  element = $selectedPayload
} | ConvertTo-Json -Depth 8 -Compress
"""


_WINDOWS_UIA_TABLE_ELEMENT_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$payloadText = [Console]::In.ReadToEnd()
$payload = $payloadText | ConvertFrom-Json
Add-Type -AssemblyName UIAutomationClient
$hwnd = [IntPtr]([Int64]$payload.window_id)
$root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
if ($null -eq $root) { throw "UIAutomation root not found: $($payload.window_id)" }
$maxDepth = [int]$payload.max_depth
$maxElements = [int]$payload.max_elements
$maxRows = [int]$payload.max_rows
$maxColumns = [int]$payload.max_columns
$textLimit = [int]$payload.text_limit
$visibleOnly = [bool]$payload.visible_only
$locator = $payload.locator
if ($null -eq $locator) { $locator = [pscustomobject]@{} }
$operation = [string]$payload.operation
$runtimeId = [string]$payload.runtime_id
$targetRow = [int]$payload.row
$columnName = [string]$payload.column
$targetColumnIndex = $null
if ($null -ne $payload.column_index) {
  try { $targetColumnIndex = [int]$payload.column_index } catch { $targetColumnIndex = $null }
}
$matchIndex = 0
try { $matchIndex = [int]$locator.element_match_index } catch {}

function Get-PropText($obj, [string]$name) {
  $prop = $obj.PSObject.Properties[$name]
  if ($null -eq $prop -or $null -eq $prop.Value) { return '' }
  return [string]$prop.Value
}

function Limit-Text([string]$value, [int]$limit) {
  if ($limit -le 0 -or $value.Length -le $limit) { return $value }
  if ($limit -le 3) { return $value.Substring(0, $limit) }
  return $value.Substring(0, $limit - 3) + '...'
}

function Test-RegexValue([string]$pattern, [string]$value) {
  if ([string]::IsNullOrEmpty($pattern)) { return $true }
  try { return [regex]::IsMatch($value, $pattern) } catch { return $false }
}

function Test-TypeMatch($obj, [string]$expected) {
  if ([string]::IsNullOrEmpty($expected)) { return $true }
  $expectedLower = $expected.ToLowerInvariant()
  foreach ($field in @('control_type', 'localized_control_type', 'role')) {
    $candidate = (Get-PropText $obj $field).ToLowerInvariant()
    if ($candidate -eq $expectedLower -or $candidate.Contains($expectedLower)) { return $true }
  }
  return $false
}

function Get-UiaRuntimeId([System.Windows.Automation.AutomationElement]$element) {
  try { return ($element.GetRuntimeId() -join '.') } catch { return '' }
}

function Get-UiaValue([System.Windows.Automation.AutomationElement]$element) {
  try {
    $patternObj = $null
    if ($element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$patternObj)) {
      return [string]$patternObj.Current.Value
    }
  } catch {}
  return ''
}

function Convert-UiaElement(
  [System.Windows.Automation.AutomationElement]$element,
  [int]$depth,
  [string]$parentId
) {
  $current = $element.Current
  $rect = $current.BoundingRectangle
  $runtime = Get-UiaRuntimeId $element
  $uiaValue = Get-UiaValue $element
  $controlType = ''
  try {
    $controlType = [string]$current.ControlType.ProgrammaticName
    $controlType = $controlType -replace '^ControlType\.', ''
  } catch {}
  return [ordered]@{
    id = $runtime
    runtime_id = $runtime
    name = [string]$current.Name
    value = $uiaValue
    text = $(if ($uiaValue) { $uiaValue } else { [string]$current.Name })
    automation_id = [string]$current.AutomationId
    control_type = $controlType
    localized_control_type = [string]$current.LocalizedControlType
    role = $controlType
    class_name = [string]$current.ClassName
    enabled = [bool]$current.IsEnabled
    visible = -not [bool]$current.IsOffscreen
    focused = [bool]$current.HasKeyboardFocus
    bounds = @{
      x = [int][Math]::Round($rect.X)
      y = [int][Math]::Round($rect.Y)
      width = [int][Math]::Round($rect.Width)
      height = [int][Math]::Round($rect.Height)
    }
    depth = $depth
    parent_id = $parentId
  }
}

function Test-LocatorMatch($obj, $locator) {
  $names = $locator.PSObject.Properties.Name
  if ($names -contains 'element_id' -and (Get-PropText $obj 'id') -ne [string]$locator.element_id) { return $false }
  if ($names -contains 'automation_id' -and (Get-PropText $obj 'automation_id') -ne [string]$locator.automation_id) { return $false }
  if ($names -contains 'name' -and (Get-PropText $obj 'name') -ne [string]$locator.name) { return $false }
  if ($names -contains 'name_contains' -and -not (Get-PropText $obj 'name').Contains([string]$locator.name_contains)) { return $false }
  if ($names -contains 'name_regex' -and -not (Test-RegexValue ([string]$locator.name_regex) (Get-PropText $obj 'name'))) { return $false }
  $elementText = Get-PropText $obj 'text'
  if ($names -contains 'text' -and $elementText -ne [string]$locator.text) { return $false }
  if ($names -contains 'text_contains' -and -not $elementText.Contains([string]$locator.text_contains)) { return $false }
  if ($names -contains 'text_regex' -and -not (Test-RegexValue ([string]$locator.text_regex) $elementText)) { return $false }
  if ($names -contains 'control_type' -and -not (Test-TypeMatch $obj ([string]$locator.control_type))) { return $false }
  if ($names -contains 'role' -and -not (Test-TypeMatch $obj ([string]$locator.role))) { return $false }
  if ($names -contains 'element_class_name') {
    $expected = ([string]$locator.element_class_name).ToLowerInvariant()
    $actual = (Get-PropText $obj 'class_name').ToLowerInvariant()
    if (-not $actual.Contains($expected)) { return $false }
  }
  return $true
}

function Find-ElementByLocator(
  [System.Windows.Automation.AutomationElement]$searchRoot,
  $locator,
  [string]$runtimeId,
  [int]$maxDepth,
  [int]$maxElements,
  [int]$matchIndex
) {
  $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
  $queue = New-Object 'System.Collections.Generic.Queue[object]'
  $queue.Enqueue([pscustomobject]@{ Element = $searchRoot; Depth = 0; Parent = '' })
  $matched = 0
  $visited = 0
  while ($queue.Count -gt 0 -and $visited -lt $maxElements) {
    $item = $queue.Dequeue()
    $element = $item.Element
    try {
      $obj = Convert-UiaElement $element ([int]$item.Depth) ([string]$item.Parent)
      $visited += 1
      $isRuntimeMatch = -not [string]::IsNullOrEmpty($runtimeId) -and [string]$obj.runtime_id -eq $runtimeId
      if ($isRuntimeMatch -or (Test-LocatorMatch $obj $locator)) {
        if ($isRuntimeMatch -or $matched -eq $matchIndex) {
          return [pscustomobject]@{ Element = $element; Payload = $obj; Visited = $visited }
        }
        $matched += 1
      }
      if ($item.Depth -lt $maxDepth) {
        $child = $walker.GetFirstChild($element)
        while ($null -ne $child) {
          $queue.Enqueue([pscustomobject]@{ Element = $child; Depth = ([int]$item.Depth + 1); Parent = [string]$obj.runtime_id })
          $child = $walker.GetNextSibling($child)
        }
      }
    } catch {}
  }
  return $null
}

function Get-CellPayload(
  [System.Windows.Automation.AutomationElement]$cell,
  [int]$rowIndex,
  [int]$columnIndex,
  [int]$textLimit
) {
  $obj = Convert-UiaElement $cell 0 ''
  $rowName = ''
  try {
    $gridItem = $null
    if ($cell.TryGetCurrentPattern([System.Windows.Automation.GridItemPattern]::Pattern, [ref]$gridItem)) {
      $rowIndex = [int]$gridItem.Current.Row
      $columnIndex = [int]$gridItem.Current.Column
    }
  } catch {}
  try {
    $tableItem = $null
    if ($cell.TryGetCurrentPattern([System.Windows.Automation.TableItemPattern]::Pattern, [ref]$tableItem)) {
      $rowHeaders = $tableItem.Current.GetRowHeaderItems()
      if ($rowHeaders -and $rowHeaders.Length -gt 0) { $rowName = [string]$rowHeaders[0].Current.Name }
    }
  } catch {}
  return [ordered]@{
    row = $rowIndex
    column_index = $columnIndex
    row_name = $rowName
    name = Limit-Text ([string]$obj.name) $textLimit
    value = Limit-Text ([string]$obj.value) $textLimit
    text = Limit-Text ([string]$obj.text) $textLimit
    automation_id = [string]$obj.automation_id
    control_type = [string]$obj.control_type
    runtime_id = [string]$obj.runtime_id
    enabled = [bool]$obj.enabled
    visible = [bool]$obj.visible
    focused = [bool]$obj.focused
    bounds = $obj.bounds
  }
}

function Get-ColumnHeaders(
  [System.Windows.Automation.AutomationElement]$tableElement,
  [int]$columnCount
) {
  $headers = New-Object System.Collections.ArrayList
  try {
    $tablePattern = $null
    if ($tableElement.TryGetCurrentPattern([System.Windows.Automation.TablePattern]::Pattern, [ref]$tablePattern)) {
      $headerItems = $tablePattern.Current.GetColumnHeaders()
      if ($headerItems) {
        for ($i = 0; $i -lt $headerItems.Length; $i++) {
          [void]$headers.Add([string]$headerItems[$i].Current.Name)
        }
      }
    }
  } catch {}
  while ($headers.Count -lt $columnCount) {
    [void]$headers.Add("Column $($headers.Count)")
  }
  return $headers
}

function Resolve-ColumnIndex($headers, [string]$columnName, $columnIndex) {
  if ($null -ne $columnIndex) { return [int]$columnIndex }
  if (-not [string]::IsNullOrEmpty($columnName)) {
    for ($i = 0; $i -lt $headers.Count; $i++) {
      if ([string]$headers[$i] -eq $columnName) { return $i }
    }
    for ($i = 0; $i -lt $headers.Count; $i++) {
      if (([string]$headers[$i]).Contains($columnName)) { return $i }
    }
  }
  throw "Table column not found: $columnName"
}

$match = Find-ElementByLocator $root $locator $runtimeId $maxDepth $maxElements $matchIndex
if ($null -eq $match) { throw "UIAutomation table element not found: locator=$($locator | ConvertTo-Json -Compress)" }
$tableElement = $match.Element
$tablePayload = $match.Payload
$gridPattern = $null
if (-not $tableElement.TryGetCurrentPattern([System.Windows.Automation.GridPattern]::Pattern, [ref]$gridPattern)) {
  throw "UIAutomation GridPattern unavailable for table element: locator=$($locator | ConvertTo-Json -Compress)"
}
$rowCount = [int]$gridPattern.Current.RowCount
$columnCount = [int]$gridPattern.Current.ColumnCount
$readRows = [Math]::Min($rowCount, [Math]::Max(0, $maxRows))
$readColumns = [Math]::Min($columnCount, [Math]::Max(0, $maxColumns))
$headers = Get-ColumnHeaders $tableElement $columnCount
$cells = New-Object System.Collections.ArrayList
$rows = New-Object System.Collections.ArrayList
for ($r = 0; $r -lt $readRows; $r++) {
  $rowCells = New-Object System.Collections.ArrayList
  for ($c = 0; $c -lt $readColumns; $c++) {
    try {
      $cell = $gridPattern.GetItem($r, $c)
      $cellPayload = Get-CellPayload $cell $r $c $textLimit
      if ((-not $visibleOnly) -or [bool]$cellPayload.visible) {
        [void]$cells.Add($cellPayload)
        [void]$rowCells.Add($cellPayload)
      }
    } catch {}
  }
  [void]$rows.Add([ordered]@{ index = $r; cells = $rowCells })
}

if ($operation -eq 'get_table') {
  [ordered]@{
    ok = $true
    operation = $operation
    method = 'uia_grid_pattern'
    fallback_required = $false
    fallback_error = ''
    element = $tablePayload
    table = [ordered]@{
      row_count = $rowCount
      column_count = $columnCount
      read_row_count = $readRows
      read_column_count = $readColumns
      columns = $headers
      rows = $rows
      cells = $cells
      visible_only = $visibleOnly
      truncated = ($rowCount -gt $readRows -or $columnCount -gt $readColumns)
    }
  } | ConvertTo-Json -Depth 10 -Compress
  return
}

if ($operation -eq 'select_cell') {
  $resolvedColumn = Resolve-ColumnIndex $headers $columnName $targetColumnIndex
  if ($targetRow -lt 0 -or $targetRow -ge $rowCount) { throw "Table row out of range: $targetRow" }
  if ($resolvedColumn -lt 0 -or $resolvedColumn -ge $columnCount) { throw "Table column out of range: $resolvedColumn" }
  $targetCell = $gridPattern.GetItem($targetRow, $resolvedColumn)
  $selectedCell = Get-CellPayload $targetCell $targetRow $resolvedColumn $textLimit
  $method = ''
  $fallbackRequired = $false
  $fallbackError = ''
  try {
    $selectionObj = $null
    if ($targetCell.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$selectionObj)) {
      $selectionObj.Select()
      $method = 'uia_selection_item_pattern'
    } else {
      $invokeObj = $null
      if ($targetCell.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$invokeObj)) {
        $invokeObj.Invoke()
        $method = 'uia_invoke_pattern'
      } else {
        $targetCell.SetFocus()
        $method = 'uia_set_focus'
        $fallbackRequired = $true
        $fallbackError = 'SelectionItemPattern and InvokePattern unavailable'
      }
    }
  } catch {
    try {
      $targetCell.SetFocus()
      $method = 'uia_set_focus'
    } catch {
      $method = 'bounds_click_fallback'
    }
    $fallbackRequired = $true
    $fallbackError = $_.Exception.Message
  }
  [ordered]@{
    ok = $true
    operation = $operation
    method = $method
    fallback_required = $fallbackRequired
    fallback_error = $fallbackError
    element = $tablePayload
    selected_cell = $selectedCell
    table = [ordered]@{
      row_count = $rowCount
      column_count = $columnCount
      columns = $headers
    }
  } | ConvertTo-Json -Depth 10 -Compress
  return
}

throw "Unsupported UIAutomation table operation: $operation"
"""


_WINDOWS_UIA_TREE_ELEMENT_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$payloadText = [Console]::In.ReadToEnd()
$payload = $payloadText | ConvertFrom-Json
Add-Type -AssemblyName UIAutomationClient
$hwnd = [IntPtr]([Int64]$payload.window_id)
$root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
if ($null -eq $root) { throw "UIAutomation root not found: $($payload.window_id)" }
$maxDepth = [int]$payload.max_depth
$maxElements = [int]$payload.max_elements
$maxNodes = [int]$payload.max_nodes
$textLimit = [int]$payload.text_limit
$locator = $payload.locator
if ($null -eq $locator) { $locator = [pscustomobject]@{} }
$operation = [string]$payload.operation
$runtimeId = [string]$payload.runtime_id
$treePath = @()
if ($null -ne $payload.tree_path) { $treePath = @($payload.tree_path) }
$matchIndex = 0
try { $matchIndex = [int]$locator.element_match_index } catch {}

function Get-PropText($obj, [string]$name) {
  $prop = $obj.PSObject.Properties[$name]
  if ($null -eq $prop -or $null -eq $prop.Value) { return '' }
  return [string]$prop.Value
}

function Limit-Text([string]$value, [int]$limit) {
  if ($limit -le 0 -or $value.Length -le $limit) { return $value }
  if ($limit -le 3) { return $value.Substring(0, $limit) }
  return $value.Substring(0, $limit - 3) + '...'
}

function Test-RegexValue([string]$pattern, [string]$value) {
  if ([string]::IsNullOrEmpty($pattern)) { return $true }
  try { return [regex]::IsMatch($value, $pattern) } catch { return $false }
}

function Test-TypeMatch($obj, [string]$expected) {
  if ([string]::IsNullOrEmpty($expected)) { return $true }
  $expectedLower = $expected.ToLowerInvariant()
  foreach ($field in @('control_type', 'localized_control_type', 'role')) {
    $candidate = (Get-PropText $obj $field).ToLowerInvariant()
    if ($candidate -eq $expectedLower -or $candidate.Contains($expectedLower)) { return $true }
  }
  return $false
}

function Get-UiaRuntimeId([System.Windows.Automation.AutomationElement]$element) {
  try { return ($element.GetRuntimeId() -join '.') } catch { return '' }
}

function Safe-Int($value) {
  try {
    $number = [double]$value
    if ([double]::IsNaN($number) -or [double]::IsInfinity($number)) { return 0 }
    return [int][Math]::Round($number)
  } catch {
    return 0
  }
}

function Convert-UiaElement(
  [System.Windows.Automation.AutomationElement]$element,
  [int]$depth,
  [string]$parentId
) {
  $current = $element.Current
  $rect = $current.BoundingRectangle
  $runtime = Get-UiaRuntimeId $element
  $controlType = ''
  try {
    $controlType = [string]$current.ControlType.ProgrammaticName
    $controlType = $controlType -replace '^ControlType\.', ''
  } catch {}
  return [ordered]@{
    id = $runtime
    runtime_id = $runtime
    name = [string]$current.Name
    value = ''
    text = [string]$current.Name
    automation_id = [string]$current.AutomationId
    control_type = $controlType
    localized_control_type = [string]$current.LocalizedControlType
    role = $controlType
    class_name = [string]$current.ClassName
    enabled = [bool]$current.IsEnabled
    visible = -not [bool]$current.IsOffscreen
    focused = [bool]$current.HasKeyboardFocus
    bounds = @{
      x = Safe-Int $rect.X
      y = Safe-Int $rect.Y
      width = Safe-Int $rect.Width
      height = Safe-Int $rect.Height
    }
    depth = $depth
    parent_id = $parentId
  }
}

function Test-LocatorMatch($obj, $locator) {
  $names = $locator.PSObject.Properties.Name
  if ($names -contains 'element_id' -and (Get-PropText $obj 'id') -ne [string]$locator.element_id) { return $false }
  if ($names -contains 'automation_id' -and (Get-PropText $obj 'automation_id') -ne [string]$locator.automation_id) { return $false }
  if ($names -contains 'name' -and (Get-PropText $obj 'name') -ne [string]$locator.name) { return $false }
  if ($names -contains 'name_contains' -and -not (Get-PropText $obj 'name').Contains([string]$locator.name_contains)) { return $false }
  if ($names -contains 'name_regex' -and -not (Test-RegexValue ([string]$locator.name_regex) (Get-PropText $obj 'name'))) { return $false }
  $elementText = Get-PropText $obj 'text'
  if ($names -contains 'text' -and $elementText -ne [string]$locator.text) { return $false }
  if ($names -contains 'text_contains' -and -not $elementText.Contains([string]$locator.text_contains)) { return $false }
  if ($names -contains 'text_regex' -and -not (Test-RegexValue ([string]$locator.text_regex) $elementText)) { return $false }
  if ($names -contains 'control_type' -and -not (Test-TypeMatch $obj ([string]$locator.control_type))) { return $false }
  if ($names -contains 'role' -and -not (Test-TypeMatch $obj ([string]$locator.role))) { return $false }
  if ($names -contains 'element_class_name') {
    $expected = ([string]$locator.element_class_name).ToLowerInvariant()
    $actual = (Get-PropText $obj 'class_name').ToLowerInvariant()
    if (-not $actual.Contains($expected)) { return $false }
  }
  return $true
}

function Find-ElementByLocator(
  [System.Windows.Automation.AutomationElement]$searchRoot,
  $locator,
  [string]$runtimeId,
  [int]$maxDepth,
  [int]$maxElements,
  [int]$matchIndex
) {
  $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
  $queue = New-Object 'System.Collections.Generic.Queue[object]'
  $queue.Enqueue([pscustomobject]@{ Element = $searchRoot; Depth = 0; Parent = '' })
  $matched = 0
  $visited = 0
  while ($queue.Count -gt 0 -and $visited -lt $maxElements) {
    $item = $queue.Dequeue()
    $element = $item.Element
    try {
      $obj = Convert-UiaElement $element ([int]$item.Depth) ([string]$item.Parent)
      $visited += 1
      $isRuntimeMatch = -not [string]::IsNullOrEmpty($runtimeId) -and [string]$obj.runtime_id -eq $runtimeId
      if ($isRuntimeMatch -or (Test-LocatorMatch $obj $locator)) {
        if ($isRuntimeMatch -or $matched -eq $matchIndex) {
          return [pscustomobject]@{ Element = $element; Payload = $obj; Visited = $visited }
        }
        $matched += 1
      }
      if ($item.Depth -lt $maxDepth) {
        $child = $walker.GetFirstChild($element)
        while ($null -ne $child) {
          $queue.Enqueue([pscustomobject]@{ Element = $child; Depth = ([int]$item.Depth + 1); Parent = [string]$obj.runtime_id })
          $child = $walker.GetNextSibling($child)
        }
      }
    } catch {}
  }
  return $null
}

function Get-TreeNodePayload(
  [System.Windows.Automation.AutomationElement]$element,
  [int]$depth,
  [string]$parentId,
  [object[]]$pathPrefix
) {
  $obj = Convert-UiaElement $element $depth $parentId
  $expanded = $false
  $leaf = $false
  try {
    $expandObj = $null
    if ($element.TryGetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern, [ref]$expandObj)) {
      $state = $expandObj.Current.ExpandCollapseState
      $expanded = $state -eq [System.Windows.Automation.ExpandCollapseState]::Expanded
      $leaf = $state -eq [System.Windows.Automation.ExpandCollapseState]::LeafNode
    }
  } catch {}
  $selected = $false
  try {
    $selectionObj = $null
    if ($element.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$selectionObj)) {
      $selected = [bool]$selectionObj.Current.IsSelected
    }
  } catch {}
  $nodePath = @($pathPrefix) + @([string]$obj.name)
  return [ordered]@{
    id = [string]$obj.id
    runtime_id = [string]$obj.runtime_id
    name = Limit-Text ([string]$obj.name) $textLimit
    text = Limit-Text ([string]$obj.text) $textLimit
    automation_id = [string]$obj.automation_id
    control_type = [string]$obj.control_type
    role = [string]$obj.role
    class_name = [string]$obj.class_name
    enabled = [bool]$obj.enabled
    visible = [bool]$obj.visible
    focused = [bool]$obj.focused
    expanded = $expanded
    leaf = $leaf
    selected = $selected
    path = $nodePath
    bounds = $obj.bounds
    depth = $depth
    parent_id = $parentId
  }
}

function Try-Expand([System.Windows.Automation.AutomationElement]$element) {
  try {
    $expandObj = $null
    if ($element.TryGetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern, [ref]$expandObj)) {
      if ($expandObj.Current.ExpandCollapseState -ne [System.Windows.Automation.ExpandCollapseState]::Expanded) {
        $expandObj.Expand()
        Start-Sleep -Milliseconds 120
      }
      return $true
    }
  } catch {}
  return $false
}

function Find-TreeChildByName(
  [System.Windows.Automation.AutomationElement]$parent,
  [string]$name,
  [int]$maxDepth,
  [int]$maxElements
) {
  $walker = [System.Windows.Automation.TreeWalker]::RawViewWalker
  $queue = New-Object 'System.Collections.Generic.Queue[object]'
  $child = $walker.GetFirstChild($parent)
  while ($null -ne $child) {
    $queue.Enqueue([pscustomobject]@{ Element = $child; Depth = 1; Parent = '' })
    $child = $walker.GetNextSibling($child)
  }
  $visited = 0
  while ($queue.Count -gt 0 -and $visited -lt $maxElements) {
    $item = $queue.Dequeue()
    $element = $item.Element
    try {
      $current = $element.Current
      $visited += 1
      if ($current.ControlType -eq [System.Windows.Automation.ControlType]::TreeItem -and [string]$current.Name -eq $name) {
        return $element
      }
      if ($item.Depth -lt $maxDepth) {
        $grandChild = $walker.GetFirstChild($element)
        while ($null -ne $grandChild) {
          $queue.Enqueue([pscustomobject]@{ Element = $grandChild; Depth = ([int]$item.Depth + 1); Parent = '' })
          $grandChild = $walker.GetNextSibling($grandChild)
        }
      }
    } catch {}
  }
  return $null
}

function Resolve-TreePath(
  [System.Windows.Automation.AutomationElement]$treeElement,
  [object[]]$path,
  [int]$maxDepth,
  [int]$maxElements
) {
  $current = $treeElement
  foreach ($part in $path) {
    Try-Expand $current | Out-Null
    $next = Find-TreeChildByName $current ([string]$part) $maxDepth $maxElements
    if ($null -eq $next) { throw "Tree node not found: $part path=$($path -join '/')" }
    $current = $next
  }
  return $current
}

function Read-TreeNodes(
  [System.Windows.Automation.AutomationElement]$treeElement,
  [int]$maxDepth,
  [int]$maxNodes
) {
  $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
  $treePayload = Convert-UiaElement $treeElement 0 ''
  $queue = New-Object 'System.Collections.Generic.Queue[object]'
  $child = $walker.GetFirstChild($treeElement)
  while ($null -ne $child) {
    $queue.Enqueue([pscustomobject]@{ Element = $child; Depth = 0; Parent = [string]$treePayload.runtime_id; Path = @() })
    $child = $walker.GetNextSibling($child)
  }
  $nodes = New-Object System.Collections.ArrayList
  while ($queue.Count -gt 0 -and $nodes.Count -lt $maxNodes) {
    $item = $queue.Dequeue()
    $element = $item.Element
    try {
      if ($element.Current.ControlType -eq [System.Windows.Automation.ControlType]::TreeItem) {
        $node = Get-TreeNodePayload $element ([int]$item.Depth) ([string]$item.Parent) @($item.Path)
        [void]$nodes.Add($node)
        if ($item.Depth -lt $maxDepth) {
          $child = $walker.GetFirstChild($element)
          while ($null -ne $child) {
            $queue.Enqueue([pscustomobject]@{ Element = $child; Depth = ([int]$item.Depth + 1); Parent = [string]$node.runtime_id; Path = @($node.path) })
            $child = $walker.GetNextSibling($child)
          }
        }
      }
    } catch {}
  }
  return [pscustomobject]@{ Nodes = $nodes; Truncated = ($queue.Count -gt 0) }
}

$match = Find-ElementByLocator $root $locator $runtimeId $maxDepth $maxElements $matchIndex
if ($null -eq $match) { throw "UIAutomation tree element not found: locator=$($locator | ConvertTo-Json -Compress)" }
$treeElement = $match.Element
$treePayload = $match.Payload

if ($operation -eq 'get_tree') {
  $treeResult = Read-TreeNodes $treeElement $maxDepth $maxNodes
  [ordered]@{
    ok = $true
    operation = $operation
    method = 'uia_tree_walker'
    fallback_required = $false
    fallback_error = ''
    element = $treePayload
    tree = [ordered]@{
      nodes = $treeResult.Nodes
      count = $treeResult.Nodes.Count
      max_nodes = $maxNodes
      truncated = [bool]$treeResult.Truncated
    }
  } | ConvertTo-Json -Depth 10 -Compress
  return
}

$targetNode = Resolve-TreePath $treeElement $treePath $maxDepth $maxElements
$targetPayload = Get-TreeNodePayload $targetNode 0 '' @()
$targetPayload['path'] = @($treePath)
$method = ''
$fallbackRequired = $false
$fallbackError = ''
try {
  if ($operation -eq 'expand_tree') {
    $expandObj = $null
    if ($targetNode.TryGetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern, [ref]$expandObj)) {
      $expandObj.Expand()
      $method = 'uia_expand_collapse_pattern'
    } else {
      $targetNode.SetFocus()
      $method = 'uia_set_focus'
      $fallbackRequired = $true
      $fallbackError = 'ExpandCollapsePattern unavailable'
    }
  } elseif ($operation -eq 'collapse_tree') {
    $expandObj = $null
    if ($targetNode.TryGetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern, [ref]$expandObj)) {
      $expandObj.Collapse()
      $method = 'uia_expand_collapse_pattern'
    } else {
      $targetNode.SetFocus()
      $method = 'uia_set_focus'
      $fallbackRequired = $true
      $fallbackError = 'ExpandCollapsePattern unavailable'
    }
  } elseif ($operation -eq 'select_tree') {
    $selectionObj = $null
    if ($targetNode.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$selectionObj)) {
      $selectionObj.Select()
      $method = 'uia_selection_item_pattern'
      try {
        $legacyObj = $null
        if ($targetNode.TryGetCurrentPattern([System.Windows.Automation.LegacyIAccessiblePattern]::Pattern, [ref]$legacyObj)) {
          $legacyObj.DoDefaultAction()
          $method = 'uia_selection_item_pattern+legacy_iaccessible_default_action'
        }
      } catch {}
    } else {
      $legacyObj = $null
      if ($targetNode.TryGetCurrentPattern([System.Windows.Automation.LegacyIAccessiblePattern]::Pattern, [ref]$legacyObj)) {
        $legacyObj.DoDefaultAction()
        $method = 'legacy_iaccessible_default_action'
      } else {
        $targetNode.SetFocus()
        $method = 'uia_set_focus'
        $fallbackRequired = $true
        $fallbackError = 'SelectionItemPattern unavailable'
      }
    }
  } else {
    throw "Unsupported UIAutomation tree operation: $operation"
  }
} catch {
  try {
    $targetNode.SetFocus()
    $method = 'uia_set_focus'
  } catch {
    $method = 'bounds_click_fallback'
  }
  $fallbackRequired = $true
  $fallbackError = $_.Exception.Message
}

[ordered]@{
  ok = $true
  operation = $operation
  method = $method
  fallback_required = $fallbackRequired
  fallback_error = $fallbackError
  element = $treePayload
  tree_node = $targetPayload
} | ConvertTo-Json -Depth 10 -Compress
"""


_WINDOWS_UIA_MENU_ELEMENT_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$payloadText = [Console]::In.ReadToEnd()
$payload = $payloadText | ConvertFrom-Json
Add-Type -AssemblyName UIAutomationClient
$hwnd = [IntPtr]([Int64]$payload.window_id)
$root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
if ($null -eq $root) { throw "UIAutomation root not found: $($payload.window_id)" }
$menuPath = @()
if ($null -ne $payload.menu_path) { $menuPath = @($payload.menu_path) }
if ($menuPath.Count -lt 1) { throw "menu_path is required" }
$maxDepth = [int]$payload.max_depth
$maxElements = [int]$payload.max_elements
$searchGlobal = [bool]$payload.search_global
$desktopRoot = [System.Windows.Automation.AutomationElement]::RootElement

function Get-UiaRuntimeId([System.Windows.Automation.AutomationElement]$element) {
  try { return ($element.GetRuntimeId() -join '.') } catch { return '' }
}

function Safe-Int($value) {
  try {
    $number = [double]$value
    if ([double]::IsNaN($number) -or [double]::IsInfinity($number)) { return 0 }
    return [int][Math]::Round($number)
  } catch {
    return 0
  }
}

function Convert-UiaElement(
  [System.Windows.Automation.AutomationElement]$element,
  [int]$depth,
  [string]$parentId
) {
  $current = $element.Current
  $rect = $current.BoundingRectangle
  $runtime = Get-UiaRuntimeId $element
  $controlType = ''
  try {
    $controlType = [string]$current.ControlType.ProgrammaticName
    $controlType = $controlType -replace '^ControlType\.', ''
  } catch {}
  return [ordered]@{
    id = $runtime
    runtime_id = $runtime
    name = [string]$current.Name
    value = ''
    text = [string]$current.Name
    automation_id = [string]$current.AutomationId
    control_type = $controlType
    localized_control_type = [string]$current.LocalizedControlType
    role = $controlType
    class_name = [string]$current.ClassName
    enabled = [bool]$current.IsEnabled
    visible = -not [bool]$current.IsOffscreen
    focused = [bool]$current.HasKeyboardFocus
    bounds = @{
      x = Safe-Int $rect.X
      y = Safe-Int $rect.Y
      width = Safe-Int $rect.Width
      height = Safe-Int $rect.Height
    }
    depth = $depth
    parent_id = $parentId
  }
}

function Find-MenuItemByNameWithWalker(
  [System.Windows.Automation.AutomationElement]$searchRoot,
  [string]$name,
  [int]$maxDepth,
  [int]$maxElements,
  [System.Windows.Automation.TreeWalker]$walker
) {
  $queue = New-Object 'System.Collections.Generic.Queue[object]'
  $queue.Enqueue([pscustomobject]@{ Element = $searchRoot; Depth = 0; Parent = '' })
  $visited = 0
  while ($queue.Count -gt 0 -and $visited -lt $maxElements) {
    $item = $queue.Dequeue()
    $element = $item.Element
    try {
      $current = $element.Current
      $visited += 1
      if ($current.ControlType -eq [System.Windows.Automation.ControlType]::MenuItem -and [string]$current.Name -eq $name) {
        return $element
      }
      if ($item.Depth -lt $maxDepth) {
        $child = $walker.GetFirstChild($element)
        while ($null -ne $child) {
          $queue.Enqueue([pscustomobject]@{ Element = $child; Depth = ([int]$item.Depth + 1); Parent = '' })
          $child = $walker.GetNextSibling($child)
        }
      }
    } catch {}
  }
  return $null
}

function Find-MenuItemByName(
  [System.Windows.Automation.AutomationElement]$searchRoot,
  [string]$name,
  [int]$maxDepth,
  [int]$maxElements
) {
  foreach ($walker in @(
    [System.Windows.Automation.TreeWalker]::ControlViewWalker,
    [System.Windows.Automation.TreeWalker]::RawViewWalker
  )) {
    $target = Find-MenuItemByNameWithWalker $searchRoot $name $maxDepth $maxElements $walker
    if ($null -ne $target) { return $target }
  }
  return $null
}

function Try-OpenMenu([System.Windows.Automation.AutomationElement]$element) {
  try {
    $expandObj = $null
    if ($element.TryGetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern, [ref]$expandObj)) {
      if ($expandObj.Current.ExpandCollapseState -ne [System.Windows.Automation.ExpandCollapseState]::Expanded) {
        $expandObj.Expand()
        Start-Sleep -Milliseconds 160
      }
      return 'uia_expand_collapse_pattern'
    }
  } catch {}
  try {
    $invokeObj = $null
    if ($element.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$invokeObj)) {
      $invokeObj.Invoke()
      Start-Sleep -Milliseconds 160
      return 'uia_invoke_pattern'
    }
  } catch {}
  try {
    $element.SetFocus()
    return 'uia_set_focus'
  } catch {}
  return 'none'
}

$currentRoot = $root
$target = $null
$openMethods = New-Object System.Collections.ArrayList
function Find-MenuItemAcrossRoots(
  [string]$name,
  [int]$maxDepth,
  [int]$maxElements,
  [bool]$searchGlobal
) {
  $roots = New-Object System.Collections.Generic.List[object]
  if ($null -ne $currentRoot) { [void]$roots.Add($currentRoot) }
  if ($root -ne $currentRoot -and $null -ne $root) { [void]$roots.Add($root) }
  if ($searchGlobal -and $null -ne $desktopRoot) { [void]$roots.Add($desktopRoot) }
  foreach ($searchRoot in $roots) {
    $candidate = Find-MenuItemByName $searchRoot $name $maxDepth $maxElements
    if ($null -ne $candidate) { return $candidate }
  }
  return $null
}
for ($i = 0; $i -lt $menuPath.Count; $i++) {
  $segment = [string]$menuPath[$i]
  $target = Find-MenuItemAcrossRoots $segment $maxDepth $maxElements $searchGlobal
  if ($null -eq $target -and $searchGlobal -and $null -ne $desktopRoot) {
    $globalDepth = [Math]::Max($maxDepth + 4, $maxDepth)
    $globalElements = [Math]::Max($maxElements * 4, $maxElements)
    $target = Find-MenuItemAcrossRoots $segment $globalDepth $globalElements $true
  }
  if ($null -eq $target) { throw "Menu item not found: $segment path=$($menuPath -join '/')" }
  if ($i -lt ($menuPath.Count - 1)) {
    [void]$openMethods.Add((Try-OpenMenu $target))
    $currentRoot = $target
  }
}

$targetPayload = Convert-UiaElement $target 0 ''
$targetPayload['path'] = @($menuPath)
$method = ''
$fallbackRequired = $false
$fallbackError = ''
try {
  $invokeObj = $null
  if ($target.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$invokeObj)) {
    $invokeObj.Invoke()
    $method = 'uia_invoke_pattern'
  } else {
    $selectionObj = $null
    if ($target.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$selectionObj)) {
      $selectionObj.Select()
      $method = 'uia_selection_item_pattern'
    } else {
      $target.SetFocus()
      $method = 'uia_set_focus'
      $fallbackRequired = $true
      $fallbackError = 'InvokePattern unavailable'
    }
  }
} catch {
  try {
    $target.SetFocus()
    $method = 'uia_set_focus'
  } catch {
    $method = 'bounds_click_fallback'
  }
  $fallbackRequired = $true
  $fallbackError = $_.Exception.Message
}

[ordered]@{
  ok = $true
  operation = 'invoke_menu'
  method = $method
  open_methods = $openMethods
  search_scope = $(if ($searchGlobal) { 'desktop_root' } else { 'window' })
  fallback_required = $fallbackRequired
  fallback_error = $fallbackError
  element = $targetPayload
} | ConvertTo-Json -Depth 8 -Compress
"""


_WINDOWS_UIA_SCROLL_ELEMENT_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$payloadText = [Console]::In.ReadToEnd()
$payload = $payloadText | ConvertFrom-Json
Add-Type -AssemblyName UIAutomationClient
$hwnd = [IntPtr]([Int64]$payload.window_id)
$root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
if ($null -eq $root) { throw "UIAutomation root not found: $($payload.window_id)" }
$maxDepth = [int]$payload.max_depth
$maxElements = [int]$payload.max_elements
$locator = $payload.locator
if ($null -eq $locator) { $locator = [pscustomobject]@{} }
$runtimeId = [string]$payload.runtime_id
$amount = $null
if ($null -ne $payload.amount) {
  try { $amount = [int]$payload.amount } catch { $amount = $null }
}
$scrollTo = [string]$payload.scroll_to
$matchIndex = 0
try { $matchIndex = [int]$locator.element_match_index } catch {}

function Get-PropText($obj, [string]$name) {
  $prop = $obj.PSObject.Properties[$name]
  if ($null -eq $prop -or $null -eq $prop.Value) { return '' }
  return [string]$prop.Value
}

function Test-RegexValue([string]$pattern, [string]$value) {
  if ([string]::IsNullOrEmpty($pattern)) { return $true }
  try { return [regex]::IsMatch($value, $pattern) } catch { return $false }
}

function Test-TypeMatch($obj, [string]$expected) {
  if ([string]::IsNullOrEmpty($expected)) { return $true }
  $expectedLower = $expected.ToLowerInvariant()
  foreach ($field in @('control_type', 'localized_control_type', 'role')) {
    $candidate = (Get-PropText $obj $field).ToLowerInvariant()
    if ($candidate -eq $expectedLower -or $candidate.Contains($expectedLower)) { return $true }
  }
  return $false
}

function Get-UiaRuntimeId([System.Windows.Automation.AutomationElement]$element) {
  try { return ($element.GetRuntimeId() -join '.') } catch { return '' }
}

function Safe-Int($value) {
  try {
    $number = [double]$value
    if ([double]::IsNaN($number) -or [double]::IsInfinity($number)) { return 0 }
    return [int][Math]::Round($number)
  } catch {
    return 0
  }
}

function Convert-UiaElement(
  [System.Windows.Automation.AutomationElement]$element,
  [int]$depth,
  [string]$parentId
) {
  $current = $element.Current
  $rect = $current.BoundingRectangle
  $runtime = Get-UiaRuntimeId $element
  $controlType = ''
  try {
    $controlType = [string]$current.ControlType.ProgrammaticName
    $controlType = $controlType -replace '^ControlType\.', ''
  } catch {}
  return [ordered]@{
    id = $runtime
    runtime_id = $runtime
    name = [string]$current.Name
    value = ''
    text = [string]$current.Name
    automation_id = [string]$current.AutomationId
    control_type = $controlType
    localized_control_type = [string]$current.LocalizedControlType
    role = $controlType
    class_name = [string]$current.ClassName
    enabled = [bool]$current.IsEnabled
    visible = -not [bool]$current.IsOffscreen
    focused = [bool]$current.HasKeyboardFocus
    bounds = @{
      x = Safe-Int $rect.X
      y = Safe-Int $rect.Y
      width = Safe-Int $rect.Width
      height = Safe-Int $rect.Height
    }
    depth = $depth
    parent_id = $parentId
  }
}

function Test-LocatorMatch($obj, $locator) {
  $names = $locator.PSObject.Properties.Name
  if ($names -contains 'element_id' -and (Get-PropText $obj 'id') -ne [string]$locator.element_id) { return $false }
  if ($names -contains 'automation_id' -and (Get-PropText $obj 'automation_id') -ne [string]$locator.automation_id) { return $false }
  if ($names -contains 'name' -and (Get-PropText $obj 'name') -ne [string]$locator.name) { return $false }
  if ($names -contains 'name_contains' -and -not (Get-PropText $obj 'name').Contains([string]$locator.name_contains)) { return $false }
  if ($names -contains 'name_regex' -and -not (Test-RegexValue ([string]$locator.name_regex) (Get-PropText $obj 'name'))) { return $false }
  $elementText = Get-PropText $obj 'text'
  if ($names -contains 'text' -and $elementText -ne [string]$locator.text) { return $false }
  if ($names -contains 'text_contains' -and -not $elementText.Contains([string]$locator.text_contains)) { return $false }
  if ($names -contains 'text_regex' -and -not (Test-RegexValue ([string]$locator.text_regex) $elementText)) { return $false }
  if ($names -contains 'control_type' -and -not (Test-TypeMatch $obj ([string]$locator.control_type))) { return $false }
  if ($names -contains 'role' -and -not (Test-TypeMatch $obj ([string]$locator.role))) { return $false }
  if ($names -contains 'element_class_name') {
    $expected = ([string]$locator.element_class_name).ToLowerInvariant()
    $actual = (Get-PropText $obj 'class_name').ToLowerInvariant()
    if (-not $actual.Contains($expected)) { return $false }
  }
  return $true
}

function Find-ElementByLocator(
  [System.Windows.Automation.AutomationElement]$searchRoot,
  $locator,
  [string]$runtimeId,
  [int]$maxDepth,
  [int]$maxElements,
  [int]$matchIndex
) {
  $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
  $queue = New-Object 'System.Collections.Generic.Queue[object]'
  $queue.Enqueue([pscustomobject]@{ Element = $searchRoot; Depth = 0; Parent = '' })
  $matched = 0
  $visited = 0
  while ($queue.Count -gt 0 -and $visited -lt $maxElements) {
    $item = $queue.Dequeue()
    $element = $item.Element
    try {
      $obj = Convert-UiaElement $element ([int]$item.Depth) ([string]$item.Parent)
      $visited += 1
      $isRuntimeMatch = -not [string]::IsNullOrEmpty($runtimeId) -and [string]$obj.runtime_id -eq $runtimeId
      if ($isRuntimeMatch -or (Test-LocatorMatch $obj $locator)) {
        if ($isRuntimeMatch -or $matched -eq $matchIndex) {
          return [pscustomobject]@{ Element = $element; Payload = $obj; Visited = $visited }
        }
        $matched += 1
      }
      if ($item.Depth -lt $maxDepth) {
        $child = $walker.GetFirstChild($element)
        while ($null -ne $child) {
          $queue.Enqueue([pscustomobject]@{ Element = $child; Depth = ([int]$item.Depth + 1); Parent = [string]$obj.runtime_id })
          $child = $walker.GetNextSibling($child)
        }
      }
    } catch {}
  }
  return $null
}

$match = Find-ElementByLocator $root $locator $runtimeId $maxDepth $maxElements $matchIndex
if ($null -eq $match) { throw "UIAutomation scroll element not found: locator=$($locator | ConvertTo-Json -Compress)" }
$targetElement = $match.Element
$targetPayload = $match.Payload
$method = ''
$fallbackRequired = $false
$fallbackError = ''
try {
  $scrollObj = $null
  if ($targetElement.TryGetCurrentPattern([System.Windows.Automation.ScrollPattern]::Pattern, [ref]$scrollObj)) {
    if (-not [string]::IsNullOrEmpty($scrollTo)) {
      $noScroll = [System.Windows.Automation.ScrollPattern]::NoScroll
      $horizontal = $noScroll
      $vertical = $noScroll
      if ($scrollTo -eq 'start' -or $scrollTo -eq 'top') { $vertical = 0 }
      elseif ($scrollTo -eq 'end' -or $scrollTo -eq 'bottom') { $vertical = 100 }
      elseif ($scrollTo -eq 'left') { $horizontal = 0 }
      elseif ($scrollTo -eq 'right') { $horizontal = 100 }
      $scrollObj.SetScrollPercent($horizontal, $vertical)
    } else {
      if ($null -eq $amount -or $amount -eq 0) { throw "amount or scroll_to is required" }
      $verticalAmount = [System.Windows.Automation.ScrollAmount]::LargeDecrement
      if ($amount -lt 0) { $verticalAmount = [System.Windows.Automation.ScrollAmount]::LargeIncrement }
      $steps = [Math]::Min([Math]::Abs($amount), 8)
      for ($i = 0; $i -lt $steps; $i++) {
        $scrollObj.Scroll([System.Windows.Automation.ScrollAmount]::NoAmount, $verticalAmount)
      }
    }
    $method = 'uia_scroll_pattern'
  } else {
    $fallbackRequired = $true
    $method = 'mouse_wheel_fallback'
    $fallbackError = 'ScrollPattern unavailable'
  }
} catch {
  $fallbackRequired = $true
  $method = 'mouse_wheel_fallback'
  $fallbackError = $_.Exception.Message
}

[ordered]@{
  ok = $true
  operation = 'scroll_element'
  method = $method
  fallback_required = $fallbackRequired
  fallback_error = $fallbackError
  element = $targetPayload
} | ConvertTo-Json -Depth 8 -Compress
"""
